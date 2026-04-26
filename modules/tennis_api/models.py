from dataclasses import dataclass, field


@dataclass
class SetScore:
    set_number: int
    first: int
    second: int

    def margin(self) -> int:
        return abs(self.first - self.second)

    def winner(self) -> str:
        """Return 'first' or 'second', or 'none' if not yet decided."""
        if self.first > self.second:
            return "first"
        if self.second > self.first:
            return "second"
        return "none"


@dataclass
class MatchState:
    match_id: str
    first_player: str
    second_player: str
    sets_first: int
    sets_second: int
    current_set: int
    games_first: int            # games won in the current (active) set
    games_second: int
    point_score: str            # "40 - 30", "AD", "0 - 0"
    serving: str                # "first" or "second"
    match_point_first: bool
    match_point_second: bool
    completed_sets: list[SetScore] = field(default_factory=list)
    tournament: str = ""

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def match_name(self) -> str:
        return f"{self.first_player} vs {self.second_player}"

    @property
    def score_summary(self) -> str:
        sets = f"Sets {self.sets_first}-{self.sets_second}"
        games = f"Games {self.games_first}-{self.games_second} (Set {self.current_set})"
        return f"{sets} | {games} | {self.point_score}"

    def game_lead(self, player: str) -> int:
        """Signed game lead in the current set for 'first' or 'second'."""
        if player == "first":
            return self.games_first - self.games_second
        return self.games_second - self.games_first

    def set_score(self, set_number: int) -> SetScore | None:
        for s in self.completed_sets:
            if s.set_number == set_number:
                return s
        return None

    def has_match_point(self, player: str) -> bool:
        return self.match_point_first if player == "first" else self.match_point_second

    def player_name(self, player: str) -> str:
        return self.first_player if player == "first" else self.second_player
