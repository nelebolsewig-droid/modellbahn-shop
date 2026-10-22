"""The import-linter contracts of pyproject.toml: they cover every module, and they bite.

``lint-imports`` checks the real code. These tests make sure the configuration keeps
meaning what docs/KONZEPT.md §3.2 says, also for modules that do not exist yet: they
evaluate the very same contracts against small hand-made import graphs.
"""

import pkgutil
import tomllib
from typing import Any, Final

import grimp
import pytest
from importlinter import configuration
from importlinter.contracts.forbidden import ForbiddenContract
from importlinter.contracts.independence import IndependenceContract
from importlinter.contracts.layers import LayersContract
from importlinter.domain.contract import Contract
from importlinter.domain.helpers import module_expressions_to_modules

import modellbahn.modules
from tests.support import BACKEND_ROOT

_CONFIG: Final = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())["tool"][
    "importlinter"
]
_CONTRACT_CLASSES: Final[dict[str, type[Contract]]] = {
    "layers": LayersContract,
    "independence": IndependenceContract,
    "forbidden": ForbiddenContract,
}
_SESSION: Final = {"root_packages": ["modellbahn"], "include_external_packages": True}
LAYERS: Final = ("api", "application", "domain", "infrastructure", "contracts")


@pytest.fixture(autouse=True, scope="module")
def _configure_import_linter() -> None:
    # What the lint-imports command does first (clock, file system, graph builder);
    # import-linter leaves this function unannotated.
    configuration.configure()  # type: ignore[no-untyped-call]


def contract(contract_id: str) -> Any:
    (options,) = [c for c in _CONFIG["contracts"] if c["id"] == contract_id]
    contract_class = _CONTRACT_CLASSES[options["type"]]
    # import-linter's own configuration reader hands scalar options over as strings.
    raw = {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in options.items()
    }
    return contract_class(name=options["name"], session_options=_SESSION, contract_options=raw)


def module_packages() -> set[str]:
    return {
        f"modellbahn.modules.{info.name}"
        for info in pkgutil.iter_modules(modellbahn.modules.__path__)
        if info.ispkg
    }


def test_all_four_rules_are_configured() -> None:
    assert {c["id"] for c in _CONFIG["contracts"]} == {
        "module-layers",
        "module-boundaries",
        "platform-knows-no-modules",
        "pure-domain",
    }
    assert _CONFIG["include_external_packages"] is True


def test_contracts_cover_every_module_package() -> None:
    """Fails if a module is added that a contract does not cover (e.g. after a
    wildcard was replaced by a list of module names)."""
    graph = grimp.build_graph("modellbahn", cache_dir=None)
    modules = module_packages()
    assert "modellbahn.modules.identity" in modules

    def resolve(expressions: Any) -> set[str]:
        return {module.name for module in module_expressions_to_modules(graph, expressions)}

    assert resolve(contract("module-layers").containers) == modules
    assert resolve(contract("module-boundaries").modules) == modules
    assert resolve(contract("pure-domain").source_modules) == {f"{m}.domain" for m in modules}


def graph_with(*imports: tuple[str, str], modules: tuple[str, ...] = ("a", "b")) -> Any:
    """An import graph of well-behaved modules plus the given ``(importer, imported)`` edges.

    Names are relative to ``modellbahn``; ``fastapi`` and ``pydantic`` are external.
    """
    graph = grimp.ImportGraph()
    for name in ("modellbahn", "modellbahn.modules", "modellbahn.platform"):
        graph.add_module(name)
    for platform_module in ("events", "http", "outbox"):
        graph.add_module(f"modellbahn.platform.{platform_module}")
    for external in ("fastapi", "pydantic"):
        graph.add_module(external, is_squashed=True)
    graph.add_import(importer="modellbahn.platform.http", imported="fastapi")

    def full(name: str) -> str:
        return name if name in {"fastapi", "pydantic"} else f"modellbahn.{name}"

    healthy: list[tuple[str, str]] = []
    for module in modules:
        package = f"modules.{module}"
        graph.add_module(full(package))
        for layer in LAYERS:
            graph.add_module(full(f"{package}.{layer}"))
        healthy += [
            (f"{package}.api", f"{package}.application"),
            (f"{package}.api", "platform.http"),
            (f"{package}.application", f"{package}.domain"),
            (f"{package}.infrastructure", f"{package}.application"),
            (f"{package}.infrastructure", f"{package}.domain"),
            (f"{package}.domain", "platform.events"),
            (f"{package}.contracts", f"{package}.infrastructure"),
            (f"{package}.contracts", f"{package}.domain"),
        ]
    for importer, imported in [*healthy, *imports]:
        graph.add_import(importer=full(importer), imported=full(imported))
    return graph


ALL_CONTRACTS: Final = (
    "module-layers",
    "module-boundaries",
    "platform-knows-no-modules",
    "pure-domain",
)


def broken_contracts(graph_factory: Any) -> set[str]:
    # Contracts may modify the graph (ignored imports), so each gets its own.
    return {
        cid for cid in ALL_CONTRACTS if not contract(cid).check(graph_factory(), verbose=False).kept
    }


def test_healthy_modules_keep_every_contract() -> None:
    assert broken_contracts(graph_with) == set()


@pytest.mark.parametrize(
    ("description", "imports", "broken"),
    [
        (
            "domain reaches up into application",
            [("modules.a.domain", "modules.a.application")],
            {"module-layers"},
        ),
        (
            "application reaches up into api",
            [("modules.a.application", "modules.a.api")],
            {"module-layers"},
        ),
        (
            "api and infrastructure are independent",
            [("modules.a.api", "modules.a.infrastructure")],
            {"module-layers"},
        ),
        (
            "one module imports another's domain",
            [("modules.a.application", "modules.b.domain")],
            {"module-boundaries"},
        ),
        (
            "one module imports another's api",
            [("modules.b.api", "modules.a.api")],
            {"module-boundaries"},
        ),
        (
            "contracts are the allowed way in, even though they use infrastructure",
            [("modules.a.application", "modules.b.contracts")],
            set(),
        ),
        (
            "the platform imports a module",
            [("platform.outbox", "modules.a.contracts")],
            {"platform-knows-no-modules"},
        ),
        (
            "the platform imports a module that domains depend on",
            [("platform.events", "modules.a.contracts")],
            # Every domain imports platform.events, so this also creates illegal chains.
            {"platform-knows-no-modules", "module-layers", "module-boundaries"},
        ),
        (
            "a domain imports a web framework",
            [("modules.a.domain", "fastapi")],
            {"pure-domain"},
        ),
        (
            "a domain reaches pydantic indirectly through the platform",
            [("platform.events", "pydantic")],
            {"pure-domain"},
        ),
        (
            "an api may use the framework",
            [("modules.a.api", "pydantic")],
            set(),
        ),
    ],
)
def test_contracts_catch_violations(
    description: str, imports: list[tuple[str, str]], broken: set[str]
) -> None:
    assert broken_contracts(lambda: graph_with(*imports)) == broken, description


def test_a_new_module_is_covered_without_configuration() -> None:
    def graph() -> Any:
        return graph_with(("modules.c.domain", "modules.a.domain"), modules=("a", "b", "c"))

    assert broken_contracts(graph) == {"module-boundaries"}


def test_every_package_of_a_module_must_be_a_known_layer() -> None:
    def graph() -> Any:
        graph = graph_with()
        graph.add_module("modellbahn.modules.a.helpers")
        return graph

    assert broken_contracts(graph) == {"module-layers"}
