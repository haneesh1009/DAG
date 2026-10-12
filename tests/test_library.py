import pytest
from netlist_dag.errors import BuildError
from netlist_dag.library import read_libraries


def library(tmp_path, body):
    path = tmp_path / "cells.lib"
    path.write_text("library(test) { " + body + " }")
    return read_libraries([path])


@pytest.mark.parametrize("body,code", [
    ('cell(X) {pin(A){direction:input;} pin(Y){direction:output;}}', "MISSING_FUNCTION"),
    ('cell(X) {pin(A){direction:input;} pin(Y){direction:output;function:"B";}}', "INVALID_FUNCTION"),
    ('cell(X) {pin(A){direction:input;} pin(Y){direction:output;function:"A";three_state:"!A";}}', "UNSUPPORTED_CELL"),
    ('cell(X) {latch(I,IN){enable:"G";data_in:"D";}}', "UNSUPPORTED_CELL"),
    ('cell(X) {ff(I,IN){clocked_on:"CK";next_state:"D";clear:"!RN";} pin(D){direction:input;} pin(CK){direction:input;} pin(RN){direction:input;} pin(Q){direction:output;function:"I";}}', "UNSUPPORTED_SEQUENTIAL"),
])
def test_rejected_semantics(tmp_path, body, code):
    cells = library(tmp_path, body)
    with pytest.raises(BuildError) as error:
        cells["X"].semantics()
    assert error.value.diagnostic.code == code


def test_duplicate_cell(tmp_path):
    with pytest.raises(BuildError) as error:
        library(tmp_path, "cell(X){} cell(X){}")
    assert error.value.diagnostic.code == "DUPLICATE_CELL"


def test_malformed(tmp_path):
    with pytest.raises(BuildError) as error:
        library(tmp_path, 'cell(X){pin(A){direction : input;')
    assert error.value.diagnostic.code == "LIBERTY_PARSE"


def test_preserve_timing_metadata(tmp_path):
    cells = library(tmp_path, '''cell(X){pin(A){direction:input;}
    pin(Y){direction:output;function:"A";timing(){related_pin:"A";timing_type:combinational;}}}''')
    assert cells["X"].pins["Y"].timing == [{"related_pin": "A", "timing_type": "combinational"}]
