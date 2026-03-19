"""Bot Application factory — creates and configures the Telegram bot.

Stores shared resources (session_factory, settings, ai_client) in bot_data
so handlers can access them via context.bot_data.
"""
import structlog
from telegram.ext import Application

from cps.ai.client import AIClient
from cps.config import Settings
from cps.db.session import create_session_factory

log = structlog.get_logger()


async def post_init(application: Application) -> None:
    """Called after Application.initialize() — set up shared resources."""
    settings: Settings = application.bot_data["settings"]
    application.bot_data["session_factory"] = create_session_factory(settings.database_url)
    application.bot_data["ai_client"] = AIClient(
        api_key=settings.siliconflow_api_key,
        base_url=settings.siliconflow_base_url,
    )
    log.info("bot_initialized", affiliate_tag=settings.affiliate_tag)

    # Register periodic jobs
    from cps.jobs.crawl_failure_notifier import crawl_failure_notifier_job
    from cps.jobs.deal_scanner import deal_scanner_job
    from cps.jobs.engagement import engagement_manager_job
    from cps.jobs.price_checker import price_checker_job

    job_queue = application.job_queue
    job_queue.run_repeating(price_checker_job, interval=300, first=60)
    job_queue.run_repeating(crawl_failure_notifier_job, interval=600, first=180)
    job_queue.run_repeating(deal_scanner_job, interval=3600, first=300)
    job_queue.run_repeating(engagement_manager_job, interval=3600, first=600)
    log.info("jobs_registered")


async def post_shutdown(application: Application) -> None:
    """Clean up on shutdown."""
    sf = application.bot_data.get("session_factory")
    if sf:
        engine = getattr(sf, "_engine", None)
        if engine:
            await engine.dispose()
    log.info("bot_shutdown")


def create_bot_app(settings: Settings) -> Application:
    """Build the fully configured bot Application."""
    from cps.bot.handlers import register_handlers

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    register_handlers(app)
    return app
