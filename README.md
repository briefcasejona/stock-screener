# Stock Screener

A personal stock screener and learning tool: quality companies at a reasonable price, valued with a reverse DCF and
bear/base/bull scenarios, with a decision journal. It runs on your own computer in its own window.

**Educational, not personal financial advice.**

## Install

Download the newest version from [Releases](../../releases/latest):

- **Windows:** `StockScreener-Setup.exe`. Windows may say it protects your PC because the app isn't from a known
  publisher: click **More info**, then **Run anyway**. No administrator rights are needed.
- **Mac (Apple chip):** `StockScreener-mac.dmg`. Open it and drag Stock Screener to Applications. The first time,
  macOS says it can't check the app: open **System Settings > Privacy & Security** and click **Open Anyway**.

Once installed, the app looks for a newer version each time it starts and installs it by itself.

The app opens in its own window when Microsoft Edge, Google Chrome or Brave is installed; otherwise it opens in your
normal browser, and **Quit the program** in the sidebar stops it.

Your journal, the companies you follow and the reports you add live in the folder `StockScreener data` in your
home folder, apart from the program, so updating or uninstalling never touches them.

## How it is built

`.github/workflows/build.yml` builds the Windows installer (PyInstaller and Inno Setup) and the Mac app on GitHub's
own machines, opens every page in a real browser, installs the Windows installer, tests an update on both, and
publishes a release when the **Run workflow** button is used (or a tag like `v2026.11.10.1` is pushed).
