# Premium Data Workspace Frontend Migration Design

Date: 2026-06-19
Status: Approved design direction, pending implementation plan

## Goal

Migrate the current static frontend in `frontend/` to a real React/Vite frontend using the same technology family as the Minerva Travel frontend, adapted to this Text-to-SQL agent use case.

The result must keep the existing agent functionality while improving the user experience and visual quality. The application should open directly into the usable chat workspace, not into a marketing page.

## Reference Projects

- Current project: `/home/kevyn/PycharmProjects/agent-txt2sql-langgraph`
- Visual and stack reference: `/home/kevyn/PycharmProjects/minerva_travel/frontend_atual/apps/web`

## Target Stack

The new frontend will use:

- React 18
- Vite
- Tailwind CSS
- shadcn/Radix-style component primitives
- lucide-react icons
- Sonner-style toasts or an equivalent local toast component
- ECharts for chart rendering, preserving the existing chart payload support
- A class-based dark mode strategy compatible with the Minerva frontend style

The Express server in `frontend/server.js` remains responsible for serving the app and proxying the existing backend API. The migration should not require backend API changes unless a bug is discovered during implementation.

## Product Direction

The selected direction is "Premium Data Workspace".

The interface should borrow Minerva's premium polish, typography discipline, tokenized theme, subtle motion, and component quality, but it should not copy the travel/storybook personality literally. This application is a data product for querying healthcare data through an agent, so the experience should feel focused, trustworthy, and operational.

The default screen is the working chat interface. The layout should prioritize fast repeated use: ask a question, inspect the answer, inspect SQL/debug details when needed, explore schema, and keep context over a session.

## Functional Parity Requirements

The migrated UI must preserve the functionality currently available in the existing frontend worktree:

- Send chat questions to `/api/query`.
- Include `question`, `session_id`, and `debug` in query requests.
- Preserve the debug toggle as a visible first-class control.
- Persist debug mode locally.
- Preserve light/dark theme switching and persistence.
- Show server health/connection status.
- Clear the current conversation.
- Show example question buttons and allow one-click prompt insertion or execution.
- Preserve local session identity and conversation history with localStorage.
- Render user, assistant, and error messages distinctly.
- Render markdown-like response content, including tables.
- Provide copy-to-clipboard actions for assistant responses.
- Show SQL output when SQL is included in the response.
- Show debug details when debug mode is enabled and debug payloads are returned.
- Render ECharts visualizations when chart payloads are returned.
- Provide a schema explorer/modal/drawer with schema loading, table listing, table search, and selected schema context.
- Show loading states while the agent is processing.
- Show toasts or clear inline feedback for errors and user actions.

The migration should preserve current behavior from the worktree as the source of truth. Features that exist only in older Git history but are absent from the current worktree are out of scope unless explicitly re-requested.

## User Experience

### Layout

The app shell has three main zones:

- Header: product identity, server status, debug toggle, theme toggle, schema action, and clear-session action.
- Sidebar: example prompts, compact schema shortcuts, and contextual helper surfaces.
- Main workspace: chat transcript, result cards, chart/table blocks, SQL/debug panels, and composer.

On desktop, the sidebar remains visible and the chat workspace uses the majority of the width. On smaller screens, the sidebar collapses into a drawer or sheet while the chat composer remains easy to reach.

### Chat

The chat remains the primary workflow. The composer should support multiline input, submit on the current established keyboard behavior, disabled/loading states, and clear visual affordances for running queries.

Messages should be readable and scannable. User messages can be visually compact. Assistant responses should support rich result blocks without turning every response into a heavy card.

### Results

SQL, debug details, charts, and tables should be rendered as structured result sections under the relevant assistant message. These sections should be collapsible or visually segmented so the answer stays readable when debug mode returns verbose data.

The debug toggle should be available in the header and its state should be obvious. When debug is off, debug panels should not clutter the transcript. When debug is on, returned debug details should be easy to inspect without hiding the answer.

### Schema Explorer

The schema experience should become a polished dialog, sheet, or drawer. It must support schema selection/loading, table search, table lists, and table details based on the current API contract.

The explorer is a tool surface, not a separate landing page. It should open quickly from the header or sidebar and return the user to the chat context.

## Visual Design

The visual language should use Minerva-inspired foundations:

- DM Sans for primary UI text.
- Optional editorial serif headings only where they improve hierarchy.
- HSL CSS variables for color tokens.
- Premium but restrained surfaces, borders, and shadows.
- Subtle background texture or layered surfaces where it helps depth.
- lucide icons for controls and state labels.
- Dark mode with equal care, not a simple inverted palette.
- Motion used for state transitions, drawers, dialogs, and message entry, without slowing down the workflow.

The palette should be adapted for a data/healthcare workspace. It can keep warmth from Minerva, but should balance it with clinical blues/teals, neutral surfaces, and accessible contrast.

## Component Architecture

The migration should break the current large static files into focused React modules:

- `src/App.jsx`: application shell and provider composition.
- `src/components/layout`: header, sidebar, workspace layout, responsive shell.
- `src/components/chat`: transcript, message item, composer, welcome state, message actions.
- `src/components/results`: markdown renderer, table renderer, SQL block, debug panel, chart renderer.
- `src/components/schema`: schema dialog/sheet, schema selector, table search, table detail views.
- `src/components/ui`: reusable shadcn-style primitives needed by this app.
- `src/hooks`: chat state, persisted session, theme, debug mode, server health, schema data.
- `src/lib/api`: typed or well-structured API helpers for query, health, and schema calls.
- `src/lib/storage`: localStorage keys and serialization helpers.
- `src/lib/rendering`: response parsing and chart/table helpers.

The goal is to avoid recreating a single large `app.js` in React form. Each module should have one clear responsibility and simple props.

## Data Flow

The chat flow should be:

1. User enters or selects a question.
2. UI creates or reuses the persisted `session_id`.
3. UI sends `{ question, session_id, debug }` to `/api/query`.
4. UI appends a loading assistant state while waiting.
5. On success, UI stores and renders the response, including answer text, SQL, debug payload, and chart payload when present.
6. On failure, UI renders an error message and shows a toast or inline error.
7. Updated conversation state is persisted locally.

Schema flow should use the existing schema endpoints exposed through the current frontend/API contract. If endpoint naming differs from the current assumptions during implementation, the implementation should follow the existing working `app.js` behavior.

## Error Handling

Network errors, server unavailable states, malformed responses, chart rendering failures, and schema loading failures should not break the whole app.

Expected behavior:

- Server health is visible in the header.
- Query failures render an error message in the transcript.
- Chart failures fall back to a readable table or a clear fallback message when possible.
- Schema failures keep the explorer open and show a retryable error state.
- Copy failures show a toast or small inline feedback.

## Accessibility and Responsiveness

The migrated frontend should preserve keyboard usability and improve semantics:

- Buttons use real button elements with labels or accessible names.
- Dialogs/sheets trap focus through Radix primitives.
- Controls have visible focus states.
- Theme/debug/status controls are understandable without color alone.
- Layout works at desktop, tablet, and mobile widths.
- Text should not overflow buttons, cards, message bubbles, or table controls.

## Testing and Verification

Implementation should include focused verification for:

- Production build succeeds.
- App loads through the Express server or the chosen development flow.
- Chat request payload includes debug and session data.
- Debug toggle persists and affects outgoing requests.
- Theme persists.
- Conversation history persists.
- Schema explorer opens and handles loading/search.
- SQL/debug/chart sections render from representative response payloads.
- Error states render without crashing.
- Responsive layout works on desktop and mobile widths.

Automated tests can be lightweight if the existing project does not have a mature frontend test harness, but the final implementation must include a browser verification pass.

## Out of Scope

- Backend agent behavior changes.
- Database query logic changes.
- Reintroducing frontend features that only exist in old Git history and not in the current worktree.
- Adding authentication, billing, or unrelated product surfaces.
- Turning the app into a marketing/landing page.

## Acceptance Criteria

The migration is complete when:

- The frontend uses the target React/Vite/Tailwind/shadcn/lucide stack.
- The application opens directly into the premium chat workspace.
- All functional parity requirements above are implemented.
- Existing API behavior is preserved.
- The UI has a cohesive premium data-workspace appearance inspired by Minerva but adapted to this agent.
- Build and browser verification pass.
