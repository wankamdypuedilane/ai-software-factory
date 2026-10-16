from ai_factory.export_index import build_export_index, module_exports
from ai_factory.implementation_prompt import build_implementation_prompt
from ai_factory.implementation_request import ImplementationTask


TEST_DATABASE = """
import { Client } from "pg";
export function testDatabaseConfiguration(env = process.env) {}
export async function openTestDatabase(env = process.env) {}
"""

ISOLATED = """
export async function prepareTestDatabase(env = process.env) {}
const internal = 1;
"""


def test_js_and_ts_export_forms_are_listed() -> None:
    content = """
export const A = 1;
export type Booking = { id: string };
export interface Port {}
export class Repo {}
export default function handler() {}
export { x, y as z } from "./other";
export * from "./all";
module.exports.legacy = 1;
"""

    assert module_exports("src/a.ts", content) == [
        "A",
        "Booking",
        "Port",
        "Repo",
        "x (re-exported from ./other)",
        "z (re-exported from ./other)",
        "* (everything from ./all)",
        "legacy",
        "default",
    ]


def test_python_lists_public_definitions_only() -> None:
    content = "def run():\n    pass\n\ndef _private():\n    pass\n\nclass Store:\n    pass\nLIMIT = 3\n"

    assert module_exports("app/core.py", content) == ["run()", "Store", "LIMIT"]


def test_non_code_files_are_skipped() -> None:
    assert module_exports("docs/readme.md", "export const A = 1") is None
    assert build_export_index({"package.json": "{}"}) == []


def test_index_names_which_helper_exports_what() -> None:
    lines = build_export_index(
        {
            "tests/helpers/test-database.mjs": TEST_DATABASE,
            "tests/helpers/isolated-postgres.mjs": ISOLATED,
        }
    )

    assert lines == [
        "- tests/helpers/isolated-postgres.mjs: prepareTestDatabase(env = process.env)",
        "- tests/helpers/test-database.mjs: testDatabaseConfiguration(env = process.env), "
        "openTestDatabase(env = process.env)",
    ]


def test_prompt_keeps_the_index_when_file_contents_are_cut() -> None:
    task = ImplementationTask(
        id="RS-MVP-004",
        agent_name="developer",
        title="Bookings",
        purpose="Persist bookings.",
    )
    workspace = {
        f"src/filler{index}.ts": "x" * 6000 for index in range(10)
    }
    workspace["tests/helpers/isolated-postgres.mjs"] = ISOLATED

    prompt = build_implementation_prompt(task, {}, workspace_files=workspace)

    assert "### Export Index" in prompt
    assert "- tests/helpers/isolated-postgres.mjs: prepareTestDatabase(env = process.env)" in prompt
    assert "further workspace files omitted" in prompt


def test_signatures_show_how_to_call_a_function() -> None:
    content = """
export function createBookingService(
  serviceRepository: ServiceRepository,
  bookingRepository: BookingRepository,
  options: {
    salonEmail: string;
  }
): BookingService {}
export const on = async (cb: (x: number) => void, opts: Map<string, number>) => cb;
"""

    assert module_exports("src/BookingService.ts", content) == [
        "createBookingService(serviceRepository: ServiceRepository, "
        "bookingRepository: BookingRepository, options: { salonEmail: string; })",
        "on(cb: (x: number) => void, opts: Map<string, number>)",
    ]
