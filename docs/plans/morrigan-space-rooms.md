# Morrigan Matrix Space Rooms

## Goal

Add bounded room lifecycle control for Morrigan under one Matrix space while keeping the current main conversation unchanged.

## Scope

- Space name: `Morrigan's House`
- Space ID: `!VwYAtMXCwnmdtPTasY:threadkeeper.amadar.xyz`
- Allowed user: `@amadar:threadkeeper.amadar.xyz`
- Default encryption: enabled
- Delete semantics: archive only (remove from space, no purge)

## Runtime Guardrails (Infra)

The deployed Morrigan container receives:

- `MATRIX_SESSION_SPACE_ID`
- `MATRIX_SESSION_SPACE_NAME`
- `MATRIX_SESSION_ALLOWED_USERS`
- `MATRIX_SESSION_DEFAULT_ENCRYPTED=true`
- `MATRIX_SESSION_ARCHIVE_MODE=remove_from_space`

These are managed in `/home/neurone/ansible/infra` and must remain aligned with this implementation.

## Implementation Plan

1. Add `matrix_session_room` tool.
2. Actions: `create`, `archive`, `merge`, `link`, `list`.
3. Enforce hard checks:
   - reject out-of-scope rooms
   - reject non-allowlisted invitees
4. Persist room registry in `$HERMES_HOME/matrix-session-rooms/registry.json`.
5. Add tests for scope, encryption, and archive semantics.

## Matrix Semantics

- "Merge" means summarize source -> destination, post pointer, archive source.
- "Archive" means unparent/remove from space; room remains recoverable by ID.

## Validation

1. Create session room from main conversation.
2. Verify room is encrypted.
3. Verify room appears under `Morrigan's House`.
4. Verify `@amadar:threadkeeper.amadar.xyz` invite behavior.
5. Archive room and verify it is removed from space but still exists.
6. Verify out-of-scope operation is refused.
