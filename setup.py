from setuptools import setup, find_packages

setup(
    name="zasi",
    version="32.0.0",
    description="Governed J.A.R.V.I.S. control-plane reference platform",
    packages=find_packages(),
    py_modules=["main"],
    include_package_data=True,
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "zasi=backend.app:run",
            "zasi-legacy=src.cli:main",
            "zasi-demo=main:legacy_demo_main",
            "zasi-backup=scripts.backup_control_plane:main",
            "zasi-outbox-worker=scripts.run_outbox_worker:main",
            "zasi-action-worker=scripts.run_action_worker:main",
        ]
    }
)
