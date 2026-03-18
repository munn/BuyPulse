"""Product routes — CRUD, search, batch ops, import."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db, log_audit
from cps.api.schemas.common import PaginatedResponse
from cps.api.schemas.product import (
    AddProductRequest,
    BatchAddRequest,
    BatchUpdateRequest,
    DeleteProductRequest,
    FetchRunItem,
    PricePoint,
    ProductDetail,
    ProductItem,
    UpdateProductRequest,
)
from cps.db.models import (
    AdminUser,
    CrawlTask,
    FetchRun,
    NotificationLog,
    PriceHistory,
    PriceMonitor,
    PriceSummary,
    Product,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=PaginatedResponse[ProductItem])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    platform: str | None = None,
    status: str | None = None,  # "active" or "inactive"
    category: str | None = None,
):
    """List products with pagination, search, and filters."""
    query = select(Product)
    count_query = select(func.count()).select_from(Product)

    # Filters
    if platform:
        query = query.where(Product.platform == platform)
        count_query = count_query.where(Product.platform == platform)
    if status == "active":
        query = query.where(Product.is_active == True)  # noqa: E712
        count_query = count_query.where(Product.is_active == True)  # noqa: E712
    elif status == "inactive":
        query = query.where(Product.is_active == False)  # noqa: E712
        count_query = count_query.where(Product.is_active == False)  # noqa: E712
    if category:
        query = query.where(Product.category == category)
        count_query = count_query.where(Product.category == category)
    if search:
        query = query.where(
            or_(
                Product.platform_id == search,
                Product.title.ilike(f"%{search}%"),
            )
        )
        count_query = count_query.where(
            or_(
                Product.platform_id == search,
                Product.title.ilike(f"%{search}%"),
            )
        )

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Product.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    products = result.scalars().all()

    # Fetch current prices for listed products
    product_ids = [p.id for p in products]
    price_map: dict[int, int | None] = {}
    if product_ids:
        price_result = await db.execute(
            select(PriceSummary.product_id, PriceSummary.current_price)
            .where(
                PriceSummary.product_id.in_(product_ids),
                PriceSummary.price_type == "amazon",
            )
        )
        price_map = dict(price_result.all())

    items = []
    for p in products:
        item = ProductItem.model_validate(p)
        item.current_price = price_map.get(p.id)
        items.append(item)

    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get product detail with price summary."""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get price summary
    price_result = await db.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product_id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = price_result.scalar_one_or_none()

    detail = ProductDetail.model_validate(product)
    if summary:
        detail.lowest_price = summary.lowest_price
        detail.highest_price = summary.highest_price
        detail.current_price = summary.current_price
    return detail


@router.get("/{product_id}/price-history", response_model=list[PricePoint])
async def get_price_history(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get price history time series."""
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.recorded_date)
    )
    rows = result.scalars().all()
    return [
        PricePoint(
            recorded_date=r.recorded_date,
            price_cents=r.price_cents,
            price_type=r.price_type,
        )
        for r in rows
    ]


@router.get("/{product_id}/fetch-runs", response_model=list[FetchRunItem])
async def get_fetch_runs(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get fetch run history for a product."""
    result = await db.execute(
        select(FetchRun)
        .where(FetchRun.product_id == product_id)
        .order_by(FetchRun.created_at.desc())
        .limit(50)
    )
    return [FetchRunItem.model_validate(r) for r in result.scalars().all()]


@router.post("")
async def add_product(
    body: AddProductRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Add a single product."""
    from cps.seeds.manager import SeedManager

    manager = SeedManager(db)
    added = await manager.add_single(body.platform_id)
    if not added:
        raise HTTPException(status_code=409, detail="Product already exists")

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "create", "product", client_ip,
                    resource_id=body.platform_id)
    await db.commit()
    return {"detail": "Product added", "platform_id": body.platform_id}


@router.post("/batch")
async def batch_add(
    body: BatchAddRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Batch add products (max 500)."""
    from cps.seeds.manager import SeedManager

    manager = SeedManager(db)
    added = 0
    skipped = 0
    for item in body.items:
        try:
            result = await manager.add_single(item.platform_id)
            if result:
                added += 1
            else:
                skipped += 1
        except ValueError:
            skipped += 1

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "create", "product", client_ip,
                    details={"added": added, "skipped": skipped, "total": len(body.items)})
    await db.commit()
    return {"added": added, "skipped": skipped, "total": len(body.items)}


@router.post("/import")
async def import_products(
    file: UploadFile,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Upload a file for async background import."""
    from cps.config import get_settings
    from cps.db.models import ImportJob

    settings = get_settings()

    # Validate file
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename")
    allowed_ext = (".txt", ".csv", ".jsonl.gz")
    if not any(file.filename.endswith(ext) for ext in allowed_ext):
        raise HTTPException(status_code=400, detail=f"Allowed: {', '.join(allowed_ext)}")

    # Create import job
    job = ImportJob(
        filename=file.filename,
        status="running",
        created_by=user.id,
    )
    db.add(job)
    await db.flush()

    # Save file
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{job.id}_{file.filename}"
    content = await file.read()
    MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB per spec
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 100MB)")
    dest.write_bytes(content)

    # Dispatch background processing
    background_tasks.add_task(_run_import, job.id, dest, settings.database_url)

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "create", "import", client_ip,
                    resource_id=str(job.id), details={"filename": file.filename})
    await db.commit()

    return {"import_job_id": job.id, "status": "running"}


async def _run_import(job_id: int, file_path, database_url: str) -> None:
    """Background task: process import file and update job progress."""
    from cps.db.models import ImportJob
    from cps.db.session import create_session_factory
    from cps.seeds.manager import SeedManager

    factory = create_session_factory(database_url)
    async with factory() as session:
        try:
            manager = SeedManager(session)
            result = await manager.import_from_file(file_path)
            await session.execute(
                update(ImportJob).where(ImportJob.id == job_id).values(
                    status="completed",
                    total=result.total,
                    processed=result.total,
                    added=result.added,
                    skipped=result.skipped,
                    completed_at=func.now(),
                )
            )
            await session.commit()
            # Delete file on success
            file_path.unlink(missing_ok=True)
        except Exception as exc:
            await session.execute(
                update(ImportJob).where(ImportJob.id == job_id).values(
                    status="failed",
                    error_message=str(exc)[:1000],
                )
            )
            await session.commit()


@router.patch("/{product_id}")
async def update_product(
    product_id: int,
    body: UpdateProductRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Update product fields (including soft-delete via is_active=false)."""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    changes = {}
    if body.is_active is not None:
        changes["is_active"] = body.is_active
    if body.title is not None:
        changes["title"] = body.title
    if body.category is not None:
        changes["category"] = body.category

    if changes:
        await db.execute(
            update(Product).where(Product.id == product_id).values(**changes)
        )

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "update", "product", client_ip,
                    resource_id=str(product_id), details=changes)
    await db.commit()
    return {"detail": "Updated"}


@router.post("/batch-update")
async def batch_update(
    body: BatchUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Batch update products (activate/deactivate, max 500)."""
    is_active = body.action == "activate"

    result = await db.execute(
        update(Product).where(Product.id.in_(body.ids)).values(is_active=is_active)
    )

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "update", "product", client_ip,
                    details={"ids": body.ids, "action": body.action, "affected": result.rowcount})
    await db.commit()
    return {"affected": result.rowcount}


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    body: DeleteProductRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Hard delete with cascade. Requires confirm=true."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirm required")

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    platform_id = product.platform_id

    # Cascade delete in order
    for model in [NotificationLog, PriceMonitor, CrawlTask, PriceSummary, FetchRun, PriceHistory]:
        await db.execute(delete(model).where(model.product_id == product_id))
    await db.execute(delete(Product).where(Product.id == product_id))

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "delete", "product", client_ip,
                    resource_id=str(product_id),
                    details={"platform_id": platform_id})
    await db.commit()
    return {"detail": "Deleted"}
