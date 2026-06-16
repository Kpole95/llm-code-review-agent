# JavaScript Best Practices — Reference

## XSS prevention
Never insert user-controlled strings into the DOM via `innerHTML` or
`document.write`. Use `textContent`, or a templating system that
auto-escapes (React JSX escapes by default unless using
`dangerouslySetInnerHTML`).

## Avoid eval() and new Function()
Same risk as Python's eval — executes arbitrary strings as code. Use
`JSON.parse()` for data instead.

## Async/await error handling
Every `await` can throw — wrap in try/catch or attach `.catch()`. Unhandled
promise rejections can crash Node processes.

## Prototype pollution
Merging untrusted objects (e.g. `Object.assign(config, req.body)`) can let
an attacker set `__proto__` and pollute unrelated objects. Validate keys
before merging user-controlled objects.

## Hardcoded secrets
API keys must come from `process.env`, never hardcoded — especially in
frontend bundles where they're publicly visible.