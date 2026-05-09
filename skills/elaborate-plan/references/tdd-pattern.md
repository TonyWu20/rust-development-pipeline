# TDD Pattern: The ch12-04 Workflow

This document codifies the Test-Driven Development workflow from the Rust book's
Chapter 12.4 ("Adding Functionality with Test-Driven Development") as a reusable
pattern for the pipeline's `lib-tdd` tasks.

## Philosophy

**Core principle**: Tests should verify behavior through public interfaces, not
implementation details. Code can change entirely; tests should not.

**Good tests** are integration-style: they exercise real code paths through
public APIs. They describe _what_ the system does, not _how_ it does it. A good
test reads like a specification -- "search returns matching lines" tells you
exactly what capability exists. These tests survive refactors because they do
not care about internal structure.

**Bad tests** are coupled to implementation. They mock internal collaborators,
test private methods, or verify through external means (like querying a database
directly instead of using the interface). The warning sign: your test breaks
when you refactor, but behavior has not changed. If you rename an internal
function and tests fail, those tests were testing implementation, not behavior.

## The Core Cycle

The ch12-04 TDD cycle has four repeating steps:

1. **Write a failing test** — specify the behavior you want. Run it, confirm it
   fails for the expected reason (the function doesn't exist yet, or returns
   wrong data).
2. **Write minimal code to pass** — do the minimum to make the test compile and
   pass. Start with a stub, then fill in logic incrementally.
3. **Refactor while green** — clean up the implementation. The test stays green
   throughout; it protects against regressions.
4. **Repeat** — add the next test, implement, refactor.

### The test IS the specification

The critical insight is that the test defines the public API *before* any
implementation exists. It specifies:

- **The function signature** — exact parameter types and return type
- **The expected behavior** — concrete inputs and outputs
- **The edge cases** — what happens with empty input, missing values, etc.

The implementation agent must treat the test code as an immutable contract: it
can only change the production code to satisfy the test, never the test itself.

### Incremental implementation

The ch12-04 chapter demonstrates this pattern with the `search` function:

```
Step 1 (RED):   Write test_search_one_result() that calls search("duct", contents)
                and expects vec!["safe, fast, productive."]
                → cargo test → fails (search doesn't exist)

Step 2 (Stub):  Define fn search(query: &str, contents: &str) -> Vec<&str> { vec![] }
                → cargo test → fails (returned empty vec, expected one line)

Step 3 (Lines): Add .lines() iteration
                → still fails (no filtering)

Step 4 (Filter):Add .contains() check
                → still fails (returns all lines, not just matches)

Step 5 (Push):  Store matching lines in a mutable vector
                → cargo test → PASSES (GREEN)

Step 6 (Clean): Refactor iterator chain, simplify
                → cargo test → still GREEN
```

Each step is verified by `cargo test`. The test never changes — only the
implementation evolves.

### Anti-Pattern: Horizontal Slices

**DO NOT write all tests first, then all implementation.** This is "horizontal
slicing" — treating RED as "write all tests" and GREEN as "write all code."

This produces weak tests:

- Tests written in bulk test _imagined_ behavior, not _actual_ behavior
- You end up testing the _shape_ of things (data structures, function
  signatures) rather than user-facing behavior
- Tests become insensitive to real changes — they pass when behavior breaks,
  fail when behavior is fine

**Correct approach**: Vertical slices via tracer bullets. One test leads to one
implementation, then repeat. Each test responds to what you learned from the
previous cycle.

```
WRONG (horizontal):
  RED:   test1, test2, test3, test4, test5
  GREEN: impl1, impl2, impl3, impl4, impl5

RIGHT (vertical):
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  RED→GREEN: test3→impl3
  ...
```

## Applying TDD in TASKS.md

When a task uses `kind: "lib-tdd"`, the TDD interface embeds the test code
that the implementation agent writes first. The task's relationship to the TDD
cycle is:

| TDD Step | TASKS.md field | What the agent does |
|----------|----------------|---------------------|
| RED | `tdd_interface.test_code` | Write the test verbatim, run `cargo test` — confirm failure |
| Stub | `tdd_interface.signature` | Write minimal implementation matching the signature, confirm test still fails behaviorally |
| GREEN | `changes[].guidance` | Implement the full logic, run `cargo test` until passing |
| Refactor | `changes[].guidance` | Clean up while `cargo test` stays green |
| Verify | `acceptance` | Confirm wiring and run full acceptance |

## Test Quality Checklist

A TDD test is a good specification when:

- [ ] It calls the function with concrete inputs
- [ ] It asserts concrete output with `assert_eq!` or similar
- [ ] The assertion would fail if the function returned the wrong value
- [ ] It covers at least one edge case (empty input, error state, boundary)
- [ ] It does NOT use `assert!(true)` or trivial always-pass assertions
- [ ] The test function name describes the behavior being tested
- [ ] The test uses the public interface only — it never reaches into internal
      modules, calls private functions, or depends on implementation details
- [ ] The test would survive an internal refactor (rename functions, extract
      helpers, reorder parameters) without changing
- [ ] The test function name describes the behavior being verified, not the
      implementation approach (e.g. `search_returns_matching_lines` not
      `search_calls_filter`)

## Good vs Bad Tests

**Good: Integration-style through public API**

```rust
#[test]
fn user_can_checkout_with_valid_cart() {
    let mut cart = Cart::new();
    cart.add(product());
    let result = checkout(&cart, &payment_method);
    assert_eq!(result.status, OrderStatus::Confirmed);
}
```

Characteristics:
- Tests behavior users/callers care about
- Uses public API only
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test

**Bad: Coupled to implementation details**

```rust
#[test]
fn checkout_calls_payment_service_process() {
    let mock = MockPaymentService::new();
    mock.expect_process().returning(|| Ok(()));
    checkout(&cart, &mock);
    // BAD: asserting on call counts/internal interactions
    assert!(mock.called_once());
}
```

```rust
// BAD: Bypasses interface to verify
#[test]
fn create_user_saves_to_database() {
    create_user(User { name: "Alice".into() });
    let row = db.query("SELECT * FROM users WHERE name = ?", &["Alice"]);
    assert!(row.is_some());
}

// GOOD: Verifies through interface
#[test]
fn create_user_makes_user_retrievable() {
    let user = create_user(User { name: "Alice".into() });
    let retrieved = get_user(user.id).unwrap();
    assert_eq!(retrieved.name, "Alice");
}
```

Red flags for bad tests:
- Mocking internal collaborators (types in the same crate)
- Testing private methods (anything not `pub`)
- Asserting on call counts or order
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means instead of the public interface

## Interface Design for Testability

Three principles for making code naturally testable in Rust:

1. **Accept dependencies, do not create them.** Pass trait objects or generics
   as parameters instead of constructing dependencies internally.

   ```rust
   // Testable -- dependency injected
   fn process_order(order: &Order, gateway: &dyn PaymentGateway) -> Result<()> { }

   // Hard to test -- dependency created internally
   fn process_order(order: &Order) -> Result<()> {
       let gateway = StripeGateway::new(env::var("STRIPE_KEY")?);
   }
   ```

2. **Return results, do not produce side effects.** Return owned values or
   `Result<T, E>`. Functions that mutate shared state through `&mut` are harder
   to verify.

   ```rust
   // Testable -- returns a value
   fn calculate_discount(cart: &Cart) -> Discount { }

   // Hard to test -- mutates shared state
   fn apply_discount(cart: &mut Cart) {
       cart.total -= discount;
   }
   ```

3. **Small surface area.** Fewer `pub` functions and trait methods means fewer
   tests needed. Fewer parameters means simpler test setup.

## Mocking: When and How

**Mock at system boundaries only:**

- External APIs (payment, email, HTTP services)
- Databases (prefer a test database when practical)
- Time/randomness (pass `Instant` or seedable `Rng` as parameters)
- Filesystem (when the test must not touch real disk)

**Never mock:**

- Your own types or modules (same crate)
- Internal collaborators
- Anything you fully control

**Design for mockability in Rust:**

Use trait-based dependency injection. Define a trait at the system boundary,
implement it for real and test contexts.

```rust
// Define a trait at the system boundary
trait PaymentClient {
    fn charge(&self, amount: u64) -> Result<Charge, PaymentError>;
}

// Production: real implementation
struct StripeClient { key: String }
impl PaymentClient for StripeClient { /* ... */ }

// Test: mock implementation
struct MockPaymentClient { /* ... */ }
impl PaymentClient for MockPaymentClient { /* ... */ }

// Injectable by generic or trait object
fn process_payment(order: &Order, client: &impl PaymentClient) -> Result<()> { }
```

Prefer **specific methods over generic fetchers**. Each endpoint gets its own
function — no conditional logic in mock setup.

```rust
// GOOD: Each function is independently mockable
trait Api {
    fn get_user(&self, id: UserId) -> Result<User>;
    fn get_orders(&self, user_id: UserId) -> Result<Vec<Order>>;
}

// BAD: Mocking requires conditional logic inside the mock
trait Api {
    fn fetch(&self, endpoint: &str) -> Result<Response>;
}
```

## Deep Modules

From "A Philosophy of Software Design": a **deep module** has a small interface
and a deep implementation — few `pub` items hiding substantial logic. A
**shallow module** has a large interface and thin implementation (many
pass-through functions, trivial delegation).

When designing interfaces and during the T4 refactor phase, ask:
- Can I reduce the number of `pub` functions?
- Can I simplify the parameter types?
- Can I hide more complexity inside?

Deep modules are the goal of refactoring — move complexity behind simple
interfaces while tests stay GREEN.

## Refactor Candidates

After the GREEN phase, look for these specific issues before declaring done:

- **Duplication** — extract into a shared function or helper
- **Long functions** — break into private helpers (tests stay on the public API)
- **Shallow modules** — combine or deepen: if a module has many `pub` items but
  each is a trivial delegation, the interface is too large
- **Feature envy** — logic that accesses another type's data more than its own;
  move it to where the data lives
- **Primitive obsession** — raw `String`, `u32`, `Vec` where a newtype would
  clarify intent and add type safety
- **Existing code** the new code reveals as problematic — if the new
  implementation highlights awkward patterns in adjacent code, flag it

## Per-Cycle Checklist

After each RED-GREEN cycle, verify:

- [ ] Test describes behavior, not implementation
- [ ] Test uses public interface only
- [ ] Test would survive internal refactor
- [ ] Code is minimal for this test — no speculation about future needs
- [ ] No speculative features added beyond what the test demands

## Anti-Patterns to Avoid

- **Write implementation first, then test** — this produces tests that validate
  the implementation rather than specify the design. The test becomes a passive
  observer instead of an active contract.
- **Trivial test** — `assert!(true)` or "test calls function but doesn't check
  output." The test must be falsifiable: it must be possible for it to fail.
- **Horizontal slicing (batch all tests then batch all code)** — write one
  test, implement to pass, then write the next. See "Anti-Pattern: Horizontal
  Slices" above for why this matters.
- **Test and implementation in separate tasks** — the implementation agent
  never sees the test, so the test can't drive the design. In this pipeline,
  both live in a single `lib-tdd` task.
- **Changing the test to match the implementation** — the test IS the
  specification. If the test is wrong, the specification is wrong. But in the
  normal TDD cycle, only the implementation changes.

## When NOT to Use This Pattern

- **CLI argument parsing** — the interface is defined by the framework (clap,
  structopt), not by a test
- **Config file generation** — I/O-heavy, hard to unit test
- **Cargo.toml edits** — not Rust code
- **I/O adapters** — database connections, HTTP clients, filesystem operations
- **main.rs wiring** — glue code that connects components
- **Any code where the interface is dictated by external constraints** rather
  than by the test

For these cases, use `kind: "direct"` (the default) with the existing
edit→check→fix loop.
