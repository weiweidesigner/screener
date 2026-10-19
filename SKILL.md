---
name: screener
description: Screen A-share, Hong Kong and US stocks with agent-selected TradingView fields, filters, sorting and pagination. Use for candidate discovery and market screening; returns source data rather than orders or buy/sell decisions.
---

# Screener

Use `scripts/run.py` as a standalone JSON CLI, or import its `Input` and `execute(service, owner, payload)` entry points. No Mentora or account service is needed. Install the pinned dependencies from this skill's `requirements.txt` in the intended Python environment.

Read `python scripts/run.py --schema` for the current argument contract; use `--describe` for market and field examples. The agent chooses the market, columns, filter operands, logical combination, ordering and pagination from the user's question and observed data. Do not turn example thresholds into mandatory selection rules.

- `operation=screen` queries `china`, `hongkong` or `america`.
- Each filter has `field`, `operator` and `value`; `match=all/any` means AND/OR. Values can refer to another field, such as `close greater SMA20`. Period suffixes such as `SMA20|1W` are supported where available upstream.
- `sortBy`, `ascending`, `limit` and `offset` control ranking and pagination. `--input` reads a JSON file, `--input-json` accepts an object, and stdin is also supported. Optional `--output` saves the same JSON result.

Rows preserve original `ticker`, normalized `symbol`, company `name`, quote currency, `update_mode` and a TradingView link. Chinese listings use names above codes when displayed; US listings use codes above names. Do not duplicate the symbol when a name is unavailable. `fetchedAt` is retrieval time, not exchange time. Preserve delayed-market labels; screening snapshots are not executable quotes or proof of a catalyst. If event verification is needed, use a separately available research tool and cite its actual evidence.

Use returned rows as evidence and decide whether to refine the query, investigate candidates or stop. Empty successful results differ from failed requests; neither licenses fabricating prices or meeting an arbitrary stock count. This skill does not access a portfolio, create an order or execute a trade.

Optional server-side configuration:

- `TRADINGVIEW_SESSION_ID`: a session cookie when needed for permitted data access. Never place it in model arguments, output or committed files. Login alone does not guarantee real-time exchange access.
- `TRADINGVIEW_SCREENER_RELAY_URL` and `TRADINGVIEW_SCREENER_TOKEN_FILE`: optional authenticated loopback relay reached through an SSH tunnel when direct connectivity is unavailable. No deployment addresses or credentials are bundled. Unavailable nodes return an explicit failure.

The upstream client is [TradingView-Screener](https://github.com/shner-elmo/TradingView-Screener); field names are documented in its [field reference](https://shner-elmo.github.io/TradingView-Screener/fields/stocks.html). Unknown fields may fail at the provider; revise arguments from actual errors rather than silently replacing criteria.
