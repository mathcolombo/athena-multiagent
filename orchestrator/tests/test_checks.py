from orchestrator.checks import is_test_file, js_tests_without_assertions


def test_js_and_python_test_files_are_recognized():
    assert is_test_file("web/tests/lib.test.js")
    assert is_test_file("services/orders/tests/test_orders.py")
    assert not is_test_file("web/public/lib.js")
    assert not is_test_file("web/tests/helpers.js")


def test_js_tests_without_assertions_are_reported():
    source = (
        'test("formata", () => {\n  assert.equal(1, 1);\n});\n\n'
        'test("vazio", () => {\n  formatMoney(1);\n});\n\n'
        "it('com ok', () => {\n  assert.ok(true);\n});\n"
    )

    assert js_tests_without_assertions(source) == ["vazio"]
