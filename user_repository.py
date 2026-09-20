from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Iterator, Any
from copy import deepcopy


@dataclass
class User:
    id: int
    name: str
    email: str
    active: bool = True
    role: str = "user"


class UserQuerySet:
    """
    Lazy, chainable query builder — Django-style.
    Doesn't execute until you iterate or call a terminal method.
    """

    def __init__(self, data_source: Callable[[], list[User]]):
        self._data_source = data_source  # deferred fetch
        self._filters: list[Callable[[User], bool]] = []
        self._excludes: list[Callable[[User], bool]] = []
        self._result_cache: list[User] | None = None

    def _clone(self) -> UserQuerySet:
        """Return a copy so chaining doesn't mutate the original."""
        clone = UserQuerySet(self._data_source)
        clone._filters = self._filters.copy()
        clone._excludes = self._excludes.copy()
        return clone

    def filter(self, **kwargs) -> UserQuerySet:
        """Add inclusion conditions. Supports field__lookup syntax."""
        clone = self._clone()
        clone._filters.append(self._build_predicate(kwargs))
        return clone

    def exclude(self, **kwargs) -> UserQuerySet:
        """Add exclusion conditions."""
        clone = self._clone()
        clone._excludes.append(self._build_predicate(kwargs))
        return clone

    def _build_predicate(self, conditions: dict[str, Any]) -> Callable[[User], bool]:
        """
        Parse Django-style lookups: field__gte, field__contains, etc.
        """
        checks = []
        for key, value in conditions.items():
            if "__" in key:
                field_name, lookup = key.rsplit("__", 1)
            else:
                field_name, lookup = key, "exact"

            checks.append((field_name, lookup, value))

        def predicate(user: User) -> bool:
            for field_name, lookup, value in checks:
                attr = getattr(user, field_name, None)
                if not self._apply_lookup(attr, lookup, value):
                    return False
            return True

        return predicate

    def _apply_lookup(self, attr: Any, lookup: str, value: Any) -> bool:
        """Evaluate a single lookup."""
        match lookup:
            case "exact":
                return attr == value
            case "iexact":
                return str(attr).lower() == str(value).lower()
            case "contains":
                return value in attr
            case "icontains":
                return str(value).lower() in str(attr).lower()
            case "gt":
                return attr > value
            case "gte":
                return attr >= value
            case "lt":
                return attr < value
            case "lte":
                return attr <= value
            case "in":
                return attr in value
            case "startswith":
                return str(attr).startswith(value)
            case "endswith":
                return str(attr).endswith(value)
            case _:
                raise ValueError(f"Unknown lookup: {lookup}")

    def _fetch(self) -> list[User]:
        """Execute the query (lazy evaluation happens here)."""
        if self._result_cache is None:
            results = self._data_source()
            for f in self._filters:
                results = [u for u in results if f(u)]
            for e in self._excludes:
                results = [u for u in results if not e(u)]
            self._result_cache = results
        return self._result_cache

    # Terminal methods — these trigger execution
    def all(self) -> list[User]:
        return self._fetch()

    def first(self) -> User | None:
        results = self._fetch()
        return results[0] if results else None

    def last(self) -> User | None:
        results = self._fetch()
        return results[-1] if results else None

    def count(self) -> int:
        return len(self._fetch())

    def exists(self) -> bool:
        return len(self._fetch()) > 0

    def __iter__(self) -> Iterator[User]:
        return iter(self._fetch())

    def __len__(self) -> int:
        return self.count()

    def __repr__(self) -> str:
        return f"<UserQuerySet ({self.count()} results)>"


class UserManager:
    """
    The 'objects' equivalent — entry point for queries.
    """

    def __init__(self, data_source: Callable[[], list[User]]):
        self._data_source = data_source

    def _queryset(self) -> UserQuerySet:
        return UserQuerySet(self._data_source)

    def all(self) -> UserQuerySet:
        return self._queryset()

    def filter(self, **kwargs) -> UserQuerySet:
        return self._queryset().filter(**kwargs)

    def exclude(self, **kwargs) -> UserQuerySet:
        return self._queryset().exclude(**kwargs)

    def get(self, **kwargs) -> User:
        """Return exactly one result, or raise."""
        results = self.filter(**kwargs).all()
        if len(results) == 0:
            raise ValueError("User not found")
        if len(results) > 1:
            raise ValueError("Multiple users found")
        return results[0]


class UserRepository:
    """
    Your repository — uses the Manager pattern.
    Swap _storage for a real DB connection when ready.
    """

    def __init__(self):
        self._storage: list[User] = []
        self.objects = UserManager(lambda: self._storage)

    def add(self, user: User) -> None:
        self._storage.append(user)

    def bulk_add(self, users: list[User]) -> None:
        self._storage.extend(users)


# --- Example usage ---
if __name__ == "__main__":
    repo = UserRepository()
    repo.bulk_add([
        User(1, "Alice", "alice@example.com", active=True, role="admin"),
        User(2, "Bob", "bob@example.com", active=True, role="user"),
        User(3, "Charlie", "charlie@test.com", active=False, role="user"),
        User(4, "Diana", "diana@example.com", active=True, role="admin"),
    ])

    # Django-style queries!
    print("Active admins:")
    for u in repo.objects.filter(active=True).filter(role="admin"):
        print(f"  {u.name}")

    print(f"\nUsers with 'example' in email: {repo.objects.filter(email__icontains='example').count()}")
    print(f"Inactive users exist? {repo.objects.filter(active=False).exists()}")
    print(f"First user: {repo.objects.all().first()}")

    # Chaining works
    query = repo.objects.filter(active=True).exclude(role="admin")
    print(f"\nActive non-admins: {[u.name for u in query]}")