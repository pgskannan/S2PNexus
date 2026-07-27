import inspect

from app.crud import supplier as supplier_crud


def test_duplicate_functions_exist():
    assert hasattr(supplier_crud, 'find_potential_duplicate_suppliers')
    assert inspect.iscoroutinefunction(supplier_crud.find_potential_duplicate_suppliers)
    assert hasattr(supplier_crud, 'merge_suppliers')
    assert inspect.iscoroutinefunction(supplier_crud.merge_suppliers)

