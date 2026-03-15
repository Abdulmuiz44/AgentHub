class ComponentRegistry:
    """Placeholder registry for future component discovery."""

    def __init__(self) -> None:
        self._items: dict[str, object] = {}

    def register(self, name: str, item: object) -> None:
        self._items[name] = item

    def get(self, name: str) -> object | None:
        return self._items.get(name)
