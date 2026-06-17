# Upgrade Runbook — 四 repo 版本協調 SOP

> **適用時機**：`trading-engine` 或任一 sibling 有 **行為/API 變更** 需要重新 pin 時。  
> **現行真相**：`requirements.txt` + 本檔「Pin 矩陣」；歷史 `docs/releases/v0.x.x.md` 保留當時記錄，**不必回改**。

---

## 1. 為什麼需要這份 Runbook？

四 repo 以 **git tag pin** 互相依賴（非 PyPI）。單獨 bump 一個 repo 的版本號而不協調，會造成：

- CI / 新 clone 裝到舊 engine → 策略讀不到新 `RiskGate` 欄位
- README 寫 v0.2.0、`requirements.txt` 寫 v0.2.2 → 人類與 Agent 各信各的
- UAT sign-off 表格與實際 tag 不一致

**結論**：對 git-pin 多 repo 架構，這是必要 SOP，不是過度流程。

---

## 2. Pin 矩陣（現行）

| Repo | Tag | 何時必須 bump |
|------|-----|---------------|
| **trading-engine** | `v0.2.2` | Kernel 行為、`RiskGate`、Settings、Protocol 變更 |
| **strategy-vwap-momentum** | `v0.1.2` | 依賴新 `RiskGate` 欄位或 engine 契約變更 |
| **trading-backtest** | `v0.1.1` | MockBroker / 回放契約變更；僅吃新 engine 時可只升 `pyproject` floor |
| **trading-app** | `v0.1.2` | 整合發布：pin、config、`uat_report`、文件 |

```text
trading-app ──pin──► trading-engine
              ├──pin──► trading-backtest ──depends──► trading-engine
              └──pin──► strategy-vwap-momentum ──depends──► trading-engine
```

---

## 3. 升級觸發條件（decision tree）

```text
engine 有變更？
├─ 否 → 只 bump 變更的 repo（strategy / backtest / app）
└─ 是
   ├─ RiskGate / Strategy Protocol / Settings 破壞性變更？
   │  ├─ 是 → engine MINOR+ → strategy 必 bump → app 必 bump pin
   │  └─ 否（patch：護欄、bugfix）→ engine PATCH → strategy 若讀新欄位則 bump → app bump pin
   └─ backtest 僅需相容？
      └─ 升 pyproject `trading-engine>=X.Y.Z` floor；無程式變更可不打 backtest tag
```

---

## 4. 逐步 SOP（以 engine v0.2.2 + app v0.1.2 為例）

### Step 0 — 開工前

- [ ] 確認 monorepo 或各 repo 本機 `main` 與遠端一致
- [ ] 記下 **現行 pin 矩陣**（上表）與本次變更範圍

### Step 1 — trading-engine（最先）

1. 實作 + `python run_tests.py` 全綠
2. `pyproject.toml` + `src/trading_engine/_version.py` 版本一致
3. `CHANGELOG.md` 條目
4. `git commit` → `git tag -a v0.2.2 -m "..."` → **先不要 push**（等下游測過）

**文件同步（現行真相，非歷史 release）**：

| 檔案 | 調整 |
|------|------|
| `README.md` | 安裝範例 `@v0.2.2`、`__version__` 註解 |
| `docs/UAT_CHECKLIST.md` | Phase A1 / Sign-off engine tag |

### Step 2 — strategy-vwap-momentum（若依賴新 RiskGate）

1. 實作策略側護欄（如 `atr_stale`、`reconnect_warmup_active`）
2. `pyproject.toml`：`trading-engine>=0.2.2,<1.0`
3. `_version.py` 與 tag 一致
4. `python run_tests.py` 全綠
5. `git tag v0.1.2`

**文件**：`README.md`、`SPEC.md` engine 版本說明。

### Step 3 — trading-backtest（視需要）

- **僅相容新 engine**：`pyproject.toml` floor → `>=0.2.2`；README 安裝範例；**可不 bump 0.1.1 tag**
- **MockBroker / 回放邏輯有改**：照 `docs/RELEASE_CHECKLIST.md` bump patch tag

### Step 4 — trading-app（整合發布）

| 檔案 | 必調 |
|------|------|
| `requirements.txt` | 三個 sibling `@vX.Y.Z` git tag |
| `pyproject.toml` | `version` + `dependencies` floor |
| `config/config.yaml` | 新 `operations.*` 鍵（若 engine 新增） |
| `CHANGELOG.md` | 新版本條目 |
| `README.md` / `SPEC.md` | Sibling pin 表 |
| `docs/UAT_CHECKLIST.md` | Phase A1 pin、Sign-off 表 |
| `docs/Architecture.md` | CI pin 一行 |
| `docs/WeeklyStatus.md` | 週報一節 + 長期提醒 pin |
| `docs/README.md` | 速查版本 |
| `docs/releases/v0.1.2.md` | **新建** release 筆記 |
| `docs/RELEASE_CHECKLIST.md` | 勾選完成項 |

測試閘門：

```bash
cd trading-app && python run_tests.py    # 預期 ~81 OK
cd ../trading-engine && python run_tests.py
cd ../strategy-vwap-momentum && python run_tests.py
```

Monorepo 開發可 `pip install -e ../trading-engine` 等，但 **commit 前仍要以 `requirements.txt` git pin 為準**。

### Step 5 — Tag 順序與 push

```bash
# 順序：engine → strategy → (backtest) → app
git -C trading-engine push origin main --tags
git -C strategy-vwap-momentum push origin main --tags
git -C trading-backtest push origin main          # 無新 tag 則只推 main
git -C trading-app push origin main --tags
```

**規則**：下游 tag **不得**指向上游尚未 push 的 commit（CI standalone clone 會失敗）。

---

## 5. 哪些文件「要改」vs「不用改」

| 類型 | 範例 | 處理 |
|------|------|------|
| **現行真相** | `requirements.txt`, `README.md`, `SPEC.md`, `UAT_CHECKLIST`, 本 Runbook, `WeeklyStatus` 長期提醒 | 每次整合發布必同步 |
| **歷史 release 筆記** | `docs/releases/v0.1.0.md`, `v0.1.1.md` | **保留**當時 pin，不重寫 |
| **Archive** | `docs/ARCHIVE/*` | 不重寫 |
| **CHANGELOG** | 各 repo `CHANGELOG.md` | 新版本追加；舊條目不改 |

---

## 6. 常見尷尬情境

### 「版本號移了，另外三個 repo 要不要調？」

| 變更性質 | engine | strategy | backtest | app |
|----------|--------|----------|----------|-----|
| engine patch + 新 RiskGate 欄位 | bump | **bump**（讀新欄位） | floor only | **bump pin** |
| engine patch，策略無感 | bump | 不 bump | floor only | bump pin |
| app-only（reporting、config） | 不 bump | 不 bump | 不 bump | bump |
| backtest MockBroker fix | 不 bump | 不 bump | bump | bump pin |

### 「README 還寫 v0.2.0」

- 若為 **頂部 Sibling packages / Install** → 必須更新（現行真相）
- 若為 **`docs/releases/v0.1.0.md` 內表格** → 刻意保留

### Monorepo vs standalone clone

| 情境 | 依賴來源 |
|------|----------|
| 本機 `-e ../trading-engine` | 目錄內程式碼 |
| CI / 新機 `pip install -r requirements.txt` | **git tag** |

兩者測試都應跑；**對外發布以 git pin 為準**。

---

## 7. Checklist 速查（複製用）

```markdown
## Release vX.Y.Z — trading-app integrator

- [ ] trading-engine tests OK → tag v____
- [ ] strategy tests OK → tag v____（若需要）
- [ ] trading-backtest floor / tag（若需要）
- [ ] trading-app: requirements.txt + pyproject + config + tests OK
- [ ] 現行真相文件已同步（README, SPEC, UAT, Architecture, WeeklyStatus）
- [ ] docs/releases/vX.Y.Z.md 已建
- [ ] push 順序：engine → strategy → backtest → app
```

---

## 8. 相關文件

- [`DOC_MAP.md`](DOC_MAP.md) — 文件職責
- [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) — tag 前機械檢查
- [`WeeklyStatus.md`](WeeklyStatus.md) — 人類交接
- [trading-engine LIVE_SAFETY](https://github.com/timhwchuang/trading-engine/blob/main/docs/LIVE_SAFETY.md) — 護欄語意