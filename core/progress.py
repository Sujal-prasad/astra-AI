import time

STAGE_PLAN = (
    ("downloading", "Downloading audio", 0.10),
    ("converting", "Converting audio", 0.04),
    ("chunking", "Splitting audio", 0.03),
    ("transcribing", "Transcribing", 0.63),
    ("analyzing", "Analyzing the meeting", 0.20),
)

STAGE_ORDER = tuple(name for name, _, _ in STAGE_PLAN)
STAGE_LABEL = {name: label for name, label, _ in STAGE_PLAN}
STAGE_WEIGHT = {name: weight for name, _, weight in STAGE_PLAN}

MEASURABLE_FRACTION = 0.04
MEASURABLE_SECONDS = 1.5
SMOOTHING = 0.4
ANCHOR_MIN_UNITS = 0.12
ETA_STAGES = frozenset({"downloading", "transcribing", "analyzing"})


def format_eta(seconds) -> str:
    if seconds is None:
        return "estimating time left"
    seconds = max(0, int(seconds))
    if seconds < 45:
        return "less than a minute left"
    minutes = round(seconds / 60)
    if minutes <= 1:
        return "about a minute left"
    if minutes < 60:
        return f"about {minutes} min left"
    hours, remaining = divmod(minutes, 60)
    return f"about {hours}h {remaining:02d}m left"


def stage_fraction(event: dict) -> float:
    if event.get("status") == "finished":
        return 1.0

    total_bytes = event.get("total_bytes") or event.get("total_bytes_estimate")
    if total_bytes:
        return min(1.0, event.get("downloaded_bytes", 0) / total_bytes)

    total_units = event.get("total")
    if total_units:
        completed = event.get("completed", max(0, event.get("current", 1) - 1))
        return min(1.0, completed / total_units)

    if "fraction" in event:
        return min(1.0, max(0.0, event["fraction"]))

    return 0.0


class ProgressTracker:
    def __init__(self, skip_download: bool = False):
        weights = {name: weight for name, weight in STAGE_WEIGHT.items()}
        if skip_download:
            weights.pop("downloading")
        scale = sum(weights.values())

        self.weights = {name: weight / scale for name, weight in weights.items()}
        self.order = [name for name in STAGE_ORDER if name in self.weights]
        self.overall = 0.0
        self.stage = None
        self.stage_started_at = time.monotonic()
        self.unit_anchor = None
        self.eta = None
        self.eta_at = time.monotonic()

    def _offset(self, stage: str) -> float:
        return sum(self.weights[name] for name in self.order[: self.order.index(stage)])

    def _weight_after(self, stage: str) -> float:
        return sum(self.weights[name] for name in self.order[self.order.index(stage) + 1 :])

    def _unit_rate_eta(self, event: dict, now: float):
        completed = event.get("completed")
        total = event.get("total")
        if completed is None or not total:
            return None

        if self.unit_anchor is None:
            if completed >= ANCHOR_MIN_UNITS:
                self.unit_anchor = (now, completed)
            return None

        anchor_time, anchor_units = self.unit_anchor
        if completed - anchor_units < ANCHOR_MIN_UNITS:
            return None

        per_unit = (now - anchor_time) / (completed - anchor_units)
        return per_unit * (total - completed), per_unit * total

    def update(self, event: dict):
        stage = event.get("stage")
        if stage not in self.weights:
            return None

        now = time.monotonic()
        if stage != self.stage:
            self.stage = stage
            self.stage_started_at = now
            self.unit_anchor = None

        fraction = stage_fraction(event)
        self.overall = max(
            self.overall,
            min(1.0, self._offset(stage) + self.weights[stage] * fraction),
        )

        if stage not in ETA_STAGES:
            return self._carry(now)

        measured = self._unit_rate_eta(event, now)
        if measured is not None:
            remaining_here, stage_total = measured
        else:
            stage_elapsed = now - self.stage_started_at
            if fraction < MEASURABLE_FRACTION or stage_elapsed < MEASURABLE_SECONDS:
                return self._carry(now)
            stage_total = stage_elapsed / fraction
            remaining_here = stage_total * (1.0 - fraction)

        after = self._weight_after(stage)
        projected = stage_total * (after / self.weights[stage])
        estimate = remaining_here + projected

        self.eta = estimate if self.eta is None else (
            (1 - SMOOTHING) * max(0.0, self.eta - (now - self.eta_at)) + SMOOTHING * estimate
        )
        self.eta_at = now
        return self.overall, STAGE_LABEL[stage], self.eta

    def _carry(self, now: float):
        if self.eta is not None:
            self.eta = max(0.0, self.eta - (now - self.eta_at))
            self.eta_at = now
        return self.overall, STAGE_LABEL[self.stage], self.eta

    def detail(self, event: dict) -> str:
        stage = event.get("stage")
        if stage == "transcribing" and event.get("total"):
            return f"chunk {event.get('current', 1)} of {event['total']}"

        if stage == "downloading":
            total = event.get("total_bytes") or event.get("total_bytes_estimate")
            if total:
                downloaded = event.get("downloaded_bytes", 0)
                return f"{downloaded / 1048576:.1f} of {total / 1048576:.1f} MB"

        if stage == "analyzing" and event.get("message"):
            return event["message"].rstrip(". ")

        return ""
