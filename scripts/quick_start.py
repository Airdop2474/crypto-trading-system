"""快速开始脚本 - 验证系统安装"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_python_version():
    """检查 Python 版本"""
    import sys
    version = sys.version_info
    print(f"[OK] Python 版本: {version.major}.{version.minor}.{version.micro}")
    if version < (3, 11):
        print("[FAIL] 错误: 需要 Python 3.11+")
        return False
    return True


def check_dependencies():
    """检查依赖是否安装"""
    required = [
        'ccxt', 'pandas', 'numpy', 'sqlalchemy',
        'redis', 'loguru', 'pytest'
    ]
    optional = ['streamlit']

    missing = []
    for package in required:
        try:
            __import__(package)
            print(f"[OK] {package}")
        except ImportError:
            print(f"[FAIL] {package} 未安装")
            missing.append(package)

    if missing:
        print(f"\n请运行: pip install {' '.join(missing)}")
        return False

    for package in optional:
        try:
            __import__(package)
            print(f"[OK] {package} (可选)")
        except ImportError:
            print(f"[WARN] {package} 未安装（监控面板可选依赖）")

    return True


def check_database():
    """检查数据库连接"""
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()

        host = os.getenv('POSTGRES_HOST', 'localhost')
        port = os.getenv('POSTGRES_PORT', '5432')

        print(f"[OK] 数据库配置: {host}:{port}")

        # 尝试连接（如果数据库正在运行）
        try:
            from sqlalchemy import create_engine
            db_url = (
                f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
                f"{os.getenv('POSTGRES_PASSWORD', 'changeme')}@"
                f"{host}:{port}/{os.getenv('POSTGRES_DB', 'crypto_trading')}"
            )
            engine = create_engine(db_url)
            with engine.connect() as conn:
                print("[OK] 数据库连接成功")
            return True
        except Exception as e:
            print(f"[WARN] 数据库未运行: {e}")
            print("  提示: 运行 docker-compose up -d 启动数据库")
            return True  # 不算致命错误

    except Exception as e:
        print(f"[FAIL] 数据库检查失败: {e}")
        return False


def check_env_file():
    """检查环境变量文件"""
    env_file = Path('.env')
    if env_file.exists():
        print("[OK] .env 文件存在")
        return True
    else:
        print("[WARN] .env 文件不存在")
        print("  提示: 复制 .env.example 到 .env 并填写配置")
        return True  # 不算致命错误


def main():
    """主函数"""
    print("=" * 60)
    print("Crypto Trading System - 安装验证")
    print("=" * 60)
    print()

    checks = [
        ("Python 版本", check_python_version),
        ("依赖包", check_dependencies),
        ("环境变量", check_env_file),
        ("数据库", check_database),
    ]

    results = []
    for name, check_func in checks:
        print(f"\n[{name}]")
        results.append(check_func())

    print("\n" + "=" * 60)
    if all(results):
        print("[OK] 所有检查通过！")
        print("\n下一步:")
        print("  1. 运行 docker-compose up -d 启动数据库")
        print("  2. 运行 python scripts/init_database.py 初始化数据库")
        print("  3. 运行 python scripts/download_data.py 下载测试数据")
    else:
        print("[FAIL] 部分检查未通过，请解决上述问题")
    print("=" * 60)


if __name__ == "__main__":
    main()
