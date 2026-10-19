# Screener

An independent, read-only stock-screening skill backed by [TradingView-Screener](https://github.com/shner-elmo/TradingView-Screener). Supports A-share, Hong Kong and US markets with structured filters chosen by an agent. No portfolio runtime, model API key or trading service is required.

```sh
git clone https://github.com/weiweidesigner/screener.git
cd screener
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/run.py --schema
.venv/bin/python scripts/run.py --describe
.venv/bin/python scripts/run.py --input-json '{"market":"china","columns":["name","description","close","change"],"limit":5}'
```

The root `SKILL.md` is the agent entry point; the whole repository can be installed as a skill directory. `scripts/run.py` also works when the skill directory is copied outside this repository. It prints one JSON object and exits nonzero on errors. Input can come from `--input`, `--input-json` or stdin. `--output` optionally saves the result.

Returned rows include normalized security codes, company names, source update modes, currency and TradingView links. Screening data can be delayed; it does not authorize or execute trades. Review `SKILL.md` for the schema, optional session/relay environment variables and evidence interpretation. Credentials stay outside the repository.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

MIT licensed. The upstream client is a separately installed MIT-licensed dependency, not vendored code. Connectivity and data entitlements depend on the provider and the execution environment.
