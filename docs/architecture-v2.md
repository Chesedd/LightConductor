# LightConductor Architecture v2 (draft)

## Goals
- Make the codebase easier to extend (new transport protocols, new storage formats, new UI flows).
- Isolate business logic from PyQt widgets and file/network implementation details.
- Enable incremental migration without a big-bang rewrite.

## Layered architecture

### 1) Domain (`src/lightconductor/domain`)
Pure business concepts, no PyQt, no filesystem, no sockets.

- Entities/value objects:
  - `Project`
  - `Master`
  - `Slave`
  - `TagType`
  - `Tag`

### 2) Application (`src/lightconductor/application`)
Use-cases and ports (interfaces).

- Use-cases:
  - create/list/delete projects
  - build show payload from project timeline
- Ports:
  - `ProjectRepositoryPort`
  - `ShowTransportPort`

### 3) Infrastructure (`src/lightconductor/infrastructure`)
Adapters for concrete technologies.

- File/json adapters for project persistence.
- UDP broadcast sender.
- Audio loading/saving adapter.
- Current audio adapter: `LibrosaAudioLoader`.

### 4) Presentation (`src/lightconductor/presentation`)
Qt UI and controllers.

- Widgets stay focused on rendering and collecting user actions.
- Controllers map UI actions to use-cases.
- Current controllers:
  - `MainScreenController`
  - `ProjectScreenController`
  - `ProjectSessionController`

## Dependency direction
`presentation -> application -> domain`
`infrastructure -> application`

Domain never depends on any outer layer.

## Migration strategy (incremental)
1. Introduce domain models and application ports/use-cases (done in this step).
2. Add infrastructure adapters that wrap current managers (`ProjectsManager`, `ProjectManager`) (in progress).
3. Move serialization/packaging logic (`dataPack`) into an application use-case (done).
4. Introduce presentation controllers and reduce business logic in widgets (in progress).
5. Replace legacy managers and direct socket/file calls from UI classes.

## Definition of done for architecture migration
- UI classes do not contain persistence/network logic.
- Project persistence is behind repository port.
- Show sending is behind transport port.
- Core timeline payload creation is unit-tested in isolation.

## QoL decisions in progress
- Slave uses one hardware control pin.
- Tag types represent LED strip segments (`segment_start` + `segment_size`) instead of extra per-type control pins.
- Each slave stores total LED count.
- New ranges are allocated only from currently free LEDs (non-overlapping selection).
- Each range can define custom topology on a grid (cell-to-led ordering) for tag editing.
- Grid may be larger than LED count, but topology editor enforces exact selected LED count per range.
- First score-writing pattern added: solid fill (paint all active LEDs with one color in tag creation).
