import inspect

from app.crud import supplier as supplier_crud


def test_hierarchy_functions_exist():
    # Basic smoke tests to ensure the hierarchy helper functions are present
    assert hasattr(supplier_crud, 'get_supplier_hierarchy')
    assert inspect.iscoroutinefunction(supplier_crud.get_supplier_hierarchy)
    assert hasattr(supplier_crud, 'set_supplier_parent')
    assert inspect.iscoroutinefunction(supplier_crud.set_supplier_parent)

