# Setup Guide

Hướng dẫn cách thiết lập môi trường trên Windows, cài dependencies bằng `uv`.

## Prerequisites
- Python 3.13+ 
- uv

## 1. Clone repo
```cmd
git clone https://github.com/haiphong-0132/legal-doc-diff-rag.git

cd legal-doc-diff-rag
```

## 1. Create virtual environment
Mở PowerShell hoặc CMD trong thư mục gốc dự án (thư mục chứa `pyproject.toml`).

PowerShell:
```powershell
python -m venv .venv

# Hoặc uv venv

.venv\Scripts\Activate.ps1
```

CMD (Windows):
```cmd
python -m venv .venv

# Hoặc uv venv

.venv\Scripts\activate
```

Để đồng bộ với môi trường của project từ `pyproject.toml`, chạy trong powerShell hoặc CMD:
```cmd
uv sync
```

## 2. Cài `uv`
`uv` là công cụ quản lý cài gói sử dụng trong repo này. Cài bằng pip:

```powershell
python -m pip install uv
```

Cách dùng `uv` để cài dependency:
```powershell
uv add <package-name>
```

```cmd
uv add <package-name>
```

Để biến folder thành package hỗ trợ import sau này, tạo `__init__.py` trống trong các thư mục con chứa code để Python nhận diện là package. Ngoài ra, để tránh lỗi ModuleNotFoundErrorchạy, chạy lệnh sau để cài project hiện tại vào môi trường ảo:
```cmd  
uv pip install -e .
```