# Python 版本 - 多Agent金融研究报告自动生成系统

## 技术栈

- **框架**: LangChain + OpenAI (LLM调用)
- **数据源**: yfinance, Tavily API, SEC EDGAR
- **结构化输出**: Pydantic v2
- **PDF生成**: ReportLab
- **异步并行**: asyncio.gather()
- **重试机制**: tenacity

## 快速开始

```bash
# 1. 安装依赖
cd python-version
pip install -r requirements.txt

# 2. 配置环境变量
cp ../.env.example .env
# 编辑 .env 填入你的 API Key

# 3. 运行
python main.py AAPL              # 分析苹果
python main.py TSLA --period 6mo # 分析特斯拉，6个月
python main.py MSFT -v           # 详细日志模式
```

## 项目结构

```
python-version/
├── main.py              # 入口文件
├── orchestrator.py      # 编排器（Pipeline+并行核心）
├── agents/
│   ├── data_collector.py    # 数据采集Agent
│   ├── sentiment_agent.py   # 舆情分析Agent
│   ├── market_analyst.py    # 市场分析Agent
│   ├── report_writer.py     # 报告撰写Agent
│   └── compliance_agent.py  # 合规审查Agent
├── tools/
│   ├── yahoo_finance_tool.py  # Yahoo Finance封装
│   ├── news_tool.py           # 新闻搜索工具
│   └── sec_edgar_tool.py      # SEC文件获取
├── models/
│   └── report_schema.py    # Pydantic数据模型
└── tests/
    └── test_agents.py      # 单元测试
```

## 核心代码解读

### 并行编排 (orchestrator.py)

```python
# Fan-out: 两个Agent并行执行，延迟 = max(Agent1, Agent2)
collected_data, sentiment = await asyncio.gather(
    self.data_collector.execute(query),
    self.sentiment_agent.execute(query),
)
```

### 运行测试

```bash
cd python-version
python -m pytest tests/ -v
```
