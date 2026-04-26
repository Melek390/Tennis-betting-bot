HELP_TEXT = (
    "<b>Tennis Betting Bot — Strategy Rules</b>\n\n"
    "<b>Rule 1</b> · Match point exists + price ≤ 75¢\n"
    "<i>Exit:</i> match point lost\n\n"
    "<b>Rule 2</b> · Leading 1-0 sets with 2+ game lead + price ≤ 65¢\n"
    "<i>Exit:</i> game lead drops below 2\n\n"
    "<b>Rule 3</b> · Sets 1-1, leading final set by 2+ games + price ≤ 62¢\n"
    "<i>Exit:</i> game lead drops below 2\n\n"
    "<b>Rule 4</b> · Won set 1 by 2+ games, leads set 2 by 1 game + price ≤ 58¢\n"
    "<i>Exit:</i> set 2 lead disappears\n\n"
    "All rules support automatic re-entry when conditions are met again."
)
