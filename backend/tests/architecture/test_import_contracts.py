"""The import-linter contracts of pyproject.toml: they cover every module, and they bite.

``lint-imports`` checks the real code. These tests make sure the configuration keeps
meaning what docs/KONZEPT.md §3.2 says, also for modules that do not exist yet: they
evaluate the very same contracts against small hand-made import graphs.
"""

import pkgutil
import tomllib
from collections.abc import Collection, Mapping
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
FULL_MODULE: Final = ("api", "application", "domain", "infrastructure", "contracts")
EXTERNAL: Final = ("fastapi", "pydantic", "sqlalchemy")


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


def graph_with(
    *imports: tuple[str, str], modules: Mapping[str, Collection[str]] | None = None
) -> Any:
    """An import graph of well-behaved modules plus the given ``(importer, imported)`` edges.

    ``modules`` maps module names to the layers they have; by default ``a`` and ``b``
    have all of them. Names are relative to ``modellbahn``; the frameworks are external.
    """
    graph = grimp.ImportGraph()
    for name in ("modellbahn", "modellbahn.modules", "modellbahn.platform"):
        graph.add_module(name)
    for platform_module in ("events", "http", "outbox"):
        graph.add_module(f"modellbahn.platform.{platform_module}")
    for external in EXTERNAL:
        graph.add_module(external, is_squashed=True)
    graph.add_import(importer="modellbahn.platform.http", imported="fastapi")

    def full(name: str) -> str:
        return name if name in EXTERNAL else f"modellbahn.{name}"

    healthy: list[tuple[str, str]] = []
    for module, layers in (modules or {"a": FULL_MODULE, "b": FULL_MODULE}).items():
        package = f"modules.{module}"
        graph.add_module(full(package))
        for layer in layers:
            graph.add_module(full(f"{package}.{layer}"))
        if "contracts" in layers:
            for part in ("events", "accounts"):
                graph.add_module(full(f"{package}.contracts.{part}"))
        healthy += [
            (importer, imported)
            for importer, imported in [
                (f"{package}.api", f"{package}.application"),
                (f"{package}.api", "platform.http"),
                (f"{package}.application", f"{package}.domain"),
                (f"{package}.infrastructure", f"{package}.application"),
                (f"{package}.infrastructure", f"{package}.domain"),
                (f"{package}.infrastructure", "sqlalchemy"),
                (f"{package}.domain", "platform.events"),
                (f"{package}.contracts.events", f"{package}.domain"),
                (f"{package}.contracts.accounts", f"{package}.infrastructure"),
                (f"{package}.contracts.accounts", "sqlalchemy"),
            ]
            if full(importer) in graph.modules and full(imported) in graph.modules
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
            "an application may use another module's database facade",
            [("modules.a.application", "modules.b.contracts.accounts")],
            set(),
        ),
        (
            "a domain may react to another module's events",
            [("modules.a.domain", "modules.b.contracts.events")],
            set(),
        ),
        (
            "a domain must not use another module's database facade",
            [("modules.a.domain", "modules.b.contracts.accounts")],
            {"pure-domain"},
        ),
        (
            "the platform imports a module",
            [("platform.outbox", "modules.a.contracts")],
            {"platform-knows-no-modules"},
        ),
        (
            "the platform imports a module that domains depend on",
            [("platform.events", "modules.a.contracts.accounts")],
            # Every domain imports platform.events, so this also creates illegal chains,
            # and the facade's SQLAlchemy reaches every domain.
            {
                "platform-knows-no-modules",
                "module-layers",
                "module-boundaries",
                "pure-domain",
            },
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
        return graph_with(
            ("modules.c.domain", "modules.a.domain"),
            modules={"a": FULL_MODULE, "b": FULL_MODULE, "c": FULL_MODULE},
        )

    assert broken_contracts(graph) == {"module-boundaries"}


def test_every_package_of_a_module_must_be_a_known_layer() -> None:
    def graph() -> Any:
        graph = graph_with()
        graph.add_module("modellbahn.modules.a.helpers")
        return graph

    assert broken_contracts(graph) == {"module-layers"}


def test_a_module_needs_no_more_than_a_domain() -> None:
    def graph() -> Any:
        return graph_with(
            modules={"a": FULL_MODULE, "b": ("domain", "application"), "c": ("domain",)}
        )

    assert broken_contracts(graph) == set()


def test_the_rules_still_bite_in_a_smaller_module() -> None:
    def graph() -> Any:
        return graph_with(
            ("modules.b.domain", "modules.b.application"),
            modules={"a": FULL_MODULE, "b": ("domain", "application")},
        )

    assert broken_contracts(graph) == {"module-layers"}
