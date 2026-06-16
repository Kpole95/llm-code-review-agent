# Python Best Practices — Reference

## SQL injection prevention
Never build SQL via string concatenation/f-strings with user input. Use
parameterized queries: `cur.execute("SELECT * FROM users WHERE id=?", (user_id,))`
instead of `cur.execute("SELECT * FROM users WHERE id=" + user_id)`.

## Avoid eval() and exec()
These run arbitrary strings as code — a direct code execution risk if any
user input reaches them. Use `ast.literal_eval()` or dict-based dispatch
instead.

## Exception handling
Avoid bare `except:` — it catches everything including KeyboardInterrupt
and silently hides bugs. Catch specific exceptions, and log if catching
broadly: `except Exception as e: logger.exception(e)`.

## Mutable default arguments
`def f(items=[]):` — the list is created ONCE at function definition and
shared across calls. Use `def f(items=None): items = items or []`.

## Context managers for resources
Always use `with open(...) as f:` so files/connections are released even
on exceptions.

## Hardcoded secrets
API keys/passwords must come from environment variables or a secrets
manager — never hardcoded in source, even in private repos.