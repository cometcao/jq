# TDX Chan Theory Plugin — Project Guide

> **Note to team:** This guide is automatically loaded by Continue.dev when working with this project. Edit as needed and commit to the repository.

---

## 1. Project Overview

### Purpose
TDXChanPlugin is a **Tongdaxin (通达信) stock analysis plugin DLL** that implements **Chan Theory (缠论)** technical analysis on K-line charts. It automatically identifies and draws:
- **Bi (笔 / Pen)** — short-term trend segments between tops and bottoms
- **XianDuan (线段 / Line Segments)** — higher-level trend structures composed of multiple pens

The plugin supports real-time updates, works with any time period (分钟线, 日线, etc.), and renders directly on the main K-chart via Tongdaxin's TDXDLL plugin interface.

### Key Technologies
| Technology | Role |
|---|---|
| **C++17/20** | Core implementation language |
| **Win32 DLL** | Tongdaxin plugin architecture (32-bit required) |
| **CMake 3.20+** | Primary build system |
| **Visual Studio 2022 Build Tools** | Windows compiler toolchain |
| **缠论 (Chan Theory)** | Domain-specific technical analysis methodology |

### High-Level Architecture
```
┌─────────────────────────────────────────────┐
│           Tongdaxin Trading Terminal         │
│              (通达信软件主程序)                │
└─────────────┬───────────────────────────────┘
              │ TDXDLL1(n, H, L, ...) API
┌─────────────▼───────────────────────────────┐
│         TDXChanPlugin.dll (this project)     │
│  ┌───────────────────────────────────────┐  │
│  │   Plugin Interface Layer (Main.cpp)    │  │
│  │  • RegisterTdxFunc() — DLL registration │  │
│  │  • TDXPlugin_Calculate() — main calc   │  │
│  │  • 5 exported funcs (Func1–Func5)      │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │   Chan Analysis Engine (ChanAnalyzer)  │  │
│  │  • K-line standardization              │  │
│  │  • Top/bottom pattern recognition      │  │
│  │  • Bi (pen) formation                  │  │
│  │  • XianDuan (line segment) formation   │  │
│  │  • Gap detection & processing          │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

---

## 2. Getting Started

### Prerequisites
- **Windows OS** (plugin targets Win32 DLL)
- **Visual Studio 2022 Build Tools** or full VS 2022 (with C++ workload)
- **CMake 3.20 or higher**
- **Tongdaxin (通达信)** trading terminal for testing
- *(Optional)* `dumpbin` for verifying DLL exports (included with VS)

### Installation & Build

**Option A: CMake Build (Recommended)**
```batch
# Run the provided build script
build_with_cmake.bat
```
Output: `TDXChanPlugin32.dll`

**Option B: Direct MSVC Build**
```batch
# Requires Visual Studio 2022 Build Tools installed at default path
build_x86.bat
```
> ⚠️ **Important:** The script assumes VS 2022 BuildTools at `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\`. Modify `build_x86.bat` if your installation path differs.

### Plugin Installation (Tongdaxin)
1. Copy `TDXChanPlugin32.dll` to your Tongdaxin `Tdx\dlls\` directory
2. Rename or ensure the DLL matches the expected plugin name (typically `TDXChanPlugin.dll`)
3. In Tongdaxin formula editor, reference functions via:
   ```tdx
   TDXDLL1(1, H, L, 0)   // Func1 - 简笔端点
   TDXDLL1(2, H, L, 0)   // Func2 - 标准笔端点 (ChanAnalyzer)
   TDXDLL1(3, BI_ARRAY, H, L)  // Func3 - 段端点 (标准画法)
   TDXDLL1(4, BI_ARRAY, H, L)  // Func4 - 段端点 (1+1终结)
   TDXDLL1(5, H, L, 0)   // Func5 - 线段端点 (ChanAnalyzer)
   ```

### Sample Formula Script
See `TDXChanPlugin_Simple_NoChinese.txt` for a complete working example:
```tdx
BI_DUAN:=TDXDLL1(1,H,L,0),NODRAW;
DRAWTEXT(BI_DUAN=1,H*1.01,'↑'),COLORYELLOW;
DRAWTEXT(BI_DUAN=-1,L*0.99,'↓'),COLORYELLOW;
UP_BI:DRAWLINE(BI_DUAN=-1,L,BI_DUAN=+1,H,0), DOTLINE,COLORYELLOW;
```

---

## 3. Project Structure

| File/Directory | Purpose |
|---|---|
| `ChanPlugin.h` | **Primary header** — All data structures, enums, and `ChanAnalyzer` class declaration. Also contains Tongdaxin `extern "C"` export interface. |
| `ChanAnalyzer.cpp` | **Core algorithm implementation** — K-line standardization, top/bottom identification, bi/segment formation, gap processing. (~31K tokens — substantial logic) |
| `Main.cpp` | **Plugin interface & entry point** — `DllMain`, `RegisterTdxFunc`, `TDXPlugin_Calculate`, memory management, and 5 formula functions (Func1–Func5). |
| `CMakeLists.txt` | CMake build configuration. Explicitly lists `ChanAnalyzer.cpp` and `Main.cpp` to avoid picking up alternate `Main_Simple.cpp`. |
| `build_with_cmake.bat` | Automated CMake build script (Win32, Release). Cleans, builds, renames output to `TDXChanPlugin32.dll`. |
| `build_x86.bat` | Direct MSVC compiler build (no CMake). Uses `cl.exe` and `link.exe` with static runtime (`/MT`). |
| `TDXChanPlugin_Simple_NoChinese.txt` | Tongdaxin formula script example showing how to call all 5 plugin functions and draw lines. |

---

## 4. Development Workflow

### Coding Conventions
- **Language:** Modern C++ (C++17 minimum, targeting C++20 compatible)
- **Naming:** Mixed conventions — structs use `PascalCase` (`KLine`, `StandardKLine`), methods use `camelCase` (`standardize()`, `defineBi()`)
- **Floating-point:** Custom epsilon-based comparisons (`float_less`, `float_equal`, etc.) with `MIN_PRICE_UNIT = 0.01` to handle financial price precision
- **Windows compatibility:** Guards for `NOMINMAX` and `WIN32_LEAN_AND_MEAN` to prevent Windows macro conflicts with `std::min/max`

### Testing Approach
- **Manual integration testing** via Tongdaxin formula editor is the primary validation method
- **Performance constraint:** Plugin processes max 400 K-lines to prevent UI freezing (see `MAX_PROCESS_COUNT` in `Main.cpp`)
- No automated unit test suite is present — consider adding GoogleTest for `ChanAnalyzer` logic

### Build & Deployment
1. Edit sources → Run `build_with_cmake.bat` or `build_x86.bat`
2. Verify exports: `dumpbin /exports TDXChanPlugin32.dll`
3. Copy DLL to Tongdaxin `dlls\` folder
4. Restart Tongdaxin or reload formula to pick up changes

### Contribution Guidelines
- Ensure Win32 (`x86`) compatibility — Tongdaxin requires 32-bit DLLs
- Do **not** introduce dynamic C++ runtime dependencies (`/MD`); use `/MT` for distribution
- Keep `ChanAnalyzer.cpp` algorithm changes synchronized with Python reference implementation (`KBar_Chan.py`) where noted in comments
- Comment complex Chan Theory logic in both Chinese and English where possible

---

## 5. Key Concepts

### Domain Terminology (Chan Theory / 缠论)

| Term | English | Description |
|---|---|---|
| **K线** | K-Line / Candlestick | OHLCV price bar |
| **包含关系** | Inclusion Relation | When one K-line's range is completely inside another's; requires standardization |
| **分型** | Top/Bottom Pattern (`TopBotType`) | `TOP` (顶分型) — local high; `BOT` (底分型) — local low |
| **笔** | Bi (Pen) | A valid trend segment connecting a top and bottom分型, following strict rules |
| **线段** | XianDuan (Line Segment) | Higher-order structure formed by consecutive pens with specific patterns |
| **缺口** | Gap | Price jump between K-lines; special handling in segment definition |

### Core Abstractions

```cpp
// Data flow through the analyzer:
std::vector<KLine> original_data      // Raw OHLC input
        ↓
std::vector<StandardKLine> standardized  // Processed for inclusions
        ↓
std::vector<StandardKLine> marked_bi     // Bi (笔) endpoints identified
        ↓
std::vector<StandardKLine> marked_xd     // XianDuan (线段) endpoints
```

### Design Patterns
- **Pimpl-like separation:** Algorithm (`ChanAnalyzer`) separated from plugin interface (`Main.cpp`)
- **Strategy pattern:** Multiple implementations for segment definition (`defineXD` vs `defineXDEnhanced` vs `*Full` variants)
- **Plugin Architecture:** Tongdaxin's established `RegisterTdxFunc` + function pointer table pattern

---

## 6. Common Tasks

### Adding a New Formula Function
1. Implement the function in `Main.cpp` following the signature:
   ```cpp
   void FuncN(int nCount, float *pOut, float *pHigh, float *pLow, float *pExtra)
   ```
2. Register it in the `Info[]` array:
   ```cpp
   {N, &FuncN},
   ```
3. Rebuild and test in Tongdaxin with `TDXDLL1(N, ...)`

### Modifying Bi/Pen Recognition Logic
- Edit `ChanAnalyzer::defineBi()` and related helper methods
- Key helpers: `markTopBot()`, `checkTopBot()`, `cleanFirstTwoTB()`

### Modifying Segment/Line Logic
- Two algorithm sets exist: standard (`defineXD`) and enhanced/full (`defineXDFull`, `defineXDEnhanced`)
- Coordinate changes across `checkXDTopBot*`, `isXDInclusionFree*`, `findXD*` family of methods

### Debugging Algorithm Behavior
- Set `ChanAnalyzer` constructor `debug = true` (requires implementing debug output)
- Use Tongdaxin's limited dataset (≤400 bars) to isolate issues
- Compare outputs against Python reference `KBar_Chan.py` where applicable

---

## 7. Troubleshooting

| Issue | Likely Cause | Solution |
|---|---|---|
| **Tongdaxin crashes when loading DLL** | 64-bit DLL compiled instead of Win32 | Ensure CMake uses `-A Win32` or `vcvars32.bat` |
| **"找不到DLL" / DLL not found** | Missing Visual C++ runtime | Use `/MT` static linking (already configured in `build_x86.bat`) |
| **Plugin returns all zeros** | `RegisterTdxFunc` not exported | Verify with `dumpbin /exports`; check `__declspec(dllexport)` |
| **Slow performance / UI freeze** | Processing too many K-lines | `MAX_PROCESS_COUNT` (400) is enforced; verify logic isn't O(n²) |
| **Incorrect bi/segment identification** | Algorithm edge case | Check `initial_state` handling in `defineBi()`/`defineXD()` |
| **Build fails with CMake** | CMake version < 3.20 or no VS generator | Upgrade CMake; ensure VS 2022 with C++ tools installed |

### Debugging Tips
- Use `dumpbin /exports TDXChanPlugin32.dll` to verify all `Func1`–`Func5` and `RegisterTdxFunc` are exported
- Temporarily add file-based logging in `ChanAnalyzer` (Tongdaxin console output is not available)
- Test with small, known datasets first before large historical data

---

## 8. References

### Internal Resources
- `TDXChanPlugin_Simple_NoChinese.txt` — Working Tongdaxin formula example
- `ChanPlugin.h` — Complete API reference for data structures and `ChanAnalyzer` class
- Inline comments in `ChanAnalyzer.cpp` reference Python implementation `KBar_Chan.py`

### External Documentation
- **Tongdaxin Plugin Development Guide** — Obtain from Tongdaxin official resources or trading software vendor
- **Chan Theory (缠论)** — Original works by 缠中说禅 (Lianyueshenchan); numerous Chinese-language technical analysis references exist

### Build Tool References
- [CMake Documentation](https://cmake.org/documentation/)
- [Microsoft C++ Compiler Options](https://docs.microsoft.com/en-us/cpp/build/reference/compiler-options)
- `dumpbin` documentation via `dumpbin /?`

---

## Appendix: Exported Function Quick Reference

| Func # | Name | Description | TDXDLL Call |
|---|---|---|---|
| 1 | `Func1` | 简笔端点 (Simple bi — 3-period high/low) | `TDXDLL1(1, H, L, 0)` |
| 2 | `Func2` | 标准笔端点 (Full ChanAnalyzer bi) | `TDXDLL1(2, H, L, 0)` |
| 3 | `Func3` | 段端点 — 标准画法 (Segment, standard) | `TDXDLL1(3, BI_ARR, H, L)` |
| 4 | `Func4` | 段端点 — 1+1终结 (Segment, 1+1 end pattern) | `TDXDLL1(4, BI_ARR, H, L)` |
| 5 | `Func5` | 线段端点 (Full ChanAnalyzer segment) | `TDXDLL1(5, H, L, 0)` |

> **Value conventions in output arrays:**
> - `+1.0` / `-1.0` = Bi top / Bi bottom
> - `+2.0` / `-2.0` = Segment top / Segment bottom
> - `+3.0` / `-3.0`, `+4.0` / `-4.0` = Alternative segment markings

---

*Guide generated for TDXChanPlugin v1.0. Last updated: {current_date}*