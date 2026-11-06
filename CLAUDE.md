# Coding Guidelines

These guidelines favor caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.
- State your assumptions explicitly.
- If multiple interpretations exist, present them instead of silently picking one.
- If something is unclear, ask.
- If a simpler approach exists, push back.

## 2. Simplicity First
- Write the minimum code that solves the problem.
- No features beyond what was asked.
- No abstractions for single-use code.
- No error handling for impossible cases.
- If it could be much shorter, rewrite it.

## 3. Surgical Changes
Touch only what you must. Clean up only your own mess.
- Change only what the request requires.
- Don't refactor or restyle adjacent code.
- Match the existing style.
- Remove only imports/variables that YOUR changes made unused.
- Mention unrelated dead code instead of deleting it.

## 4. Goal-Driven Execution
Define success criteria. Loop until verified.
- Turn vague tasks into verifiable goals.
- For a bug: write a test that reproduces it first, then make it pass.
- Loop until the criteria are verified.