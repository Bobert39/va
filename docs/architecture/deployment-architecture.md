# **Deployment Architecture**

## **MVP Deployment**

**Method:** Standalone Python application on practice PC
**Installation:** Single `install.bat` script
**Updates:** Manual download and reinstall
**Requirements:** Windows 10+, 8GB RAM, Internet connection

## **CI/CD Pipeline**

```yaml
# GitHub Actions for automated builds
name: MVP Build
on: push
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build installer
        run: |
          pip install pyinstaller
          pyinstaller --onefile src/main.py
      - name: Upload artifact
        uses: actions/upload-artifact@v2
```
