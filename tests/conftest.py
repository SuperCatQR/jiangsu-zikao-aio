"""pytest configuration: inject scripts with dash-names as importable modules."""
import sys
import importlib.util
from pathlib import Path

# Add scripts directory to path
scripts_dir = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(scripts_dir))

# Create module aliases for dash-named scripts
_script_mappings = {
    "check_source_links": "check-source-links.py",
    "bootstrap_province": "bootstrap-province.py",
    "validate_publish_gate": "validate-publish-gate.py",
    "compute_page_maturity": "compute-page-maturity.py",
}

for module_name, file_name in _script_mappings.items():
    script_path = scripts_dir / file_name
    if script_path.exists():
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
