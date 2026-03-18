#!/bin/bash
# 过夜循环爬虫 — 跑满 8 小时
# 每轮爬完所有 pending，等 5 分钟后重新把 completed 重置为 pending 再爬
# 用法: nohup bash spikes/overnight_loop.sh > spikes/overnight_loop.log 2>&1 &

END_TIME=$(($(date +%s) + 8 * 3600))  # 8 小时后停止
ROUND=0

echo "[$(date)] === 过夜爬虫启动，计划运行 8 小时 ==="

while [ $(date +%s) -lt $END_TIME ]; do
    ROUND=$((ROUND + 1))

    # 检查有多少 pending
    PENDING=$(docker exec cps-db-1 psql -U cps -d cps -t -c "SELECT count(*) FROM crawl_tasks WHERE status='pending';" 2>/dev/null | tr -d ' ')

    if [ "$PENDING" -gt 0 ]; then
        echo "[$(date)] === 第 ${ROUND} 轮：${PENDING} 个待爬 ==="
        uv run cps crawl run --limit 2000
        echo "[$(date)] === 第 ${ROUND} 轮完成 ==="
    fi

    # 检查时间
    if [ $(date +%s) -ge $END_TIME ]; then
        echo "[$(date)] === 8 小时到，停止 ==="
        break
    fi

    # 重置 completed → pending（重新爬一轮获取最新数据）
    echo "[$(date)] 等待 5 分钟后开始下一轮..."
    sleep 300

    COMPLETED=$(docker exec cps-db-1 psql -U cps -d cps -t -c "SELECT count(*) FROM crawl_tasks WHERE status='completed';" 2>/dev/null | tr -d ' ')
    echo "[$(date)] 重置 ${COMPLETED} 个 completed → pending"
    docker exec cps-db-1 psql -U cps -d cps -c "UPDATE crawl_tasks SET status='pending', retry_count=0 WHERE status='completed';" 2>/dev/null
done

# 最终统计
echo ""
echo "[$(date)] === 最终统计 ==="
docker exec cps-db-1 psql -U cps -d cps -c "
SELECT 'products' as t, count(*) FROM products
UNION ALL SELECT 'price_history', count(*) FROM price_history
UNION ALL SELECT 'price_summary', count(*) FROM price_summary
UNION ALL SELECT 'extraction_runs', count(*) FROM extraction_runs;
"
echo "[$(date)] === 过夜爬虫结束 ==="
