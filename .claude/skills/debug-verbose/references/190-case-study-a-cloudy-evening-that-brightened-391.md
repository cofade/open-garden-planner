## Case study: a cloudy evening that brightened (#391)

- **Symptom:** on the atmosphere sky an overcast sunset read 0.96–1.0 as bright as noon (the
  L5 gate is < 0.85) and the cloud deck glowed through civil twilight. The L5 weather gates
  passed because they ran on the painted sky only.
- **Wrong theories:** (1) the reviewer's: scale the clouds at a fixed high sun's gain. It
  passed the frame gate (0.56–0.59) but dimmed the deck twice — the garden at a cloudy
  sunset read a third darker than painted, and snow's dusk still rose 0.2 %. (2) Mine after
  it: the painted sun colour switching at sundown inside that gain (taking the horizon colour
  instead changed nothing).
- **Key evidence:** splitting the dusk frames into sky rows and ground rows, and rendering the
  painted sky's cloudy dusk beside them: the remaining rise sat at 0° → −1°, where the
  example's cloud lighting clamps the sun's slant at the horizon (`max(cos, 0) + 0.025`), so
  the deck kept the horizon sun's light while the look's exposure rose. Then three scales on
  the same board — the whole make-up (1.0), none (0.0), 0.7 — against the painted sky's
  sunset over noon.
- **Root cause:** the clear sky's gain at the actual sun rises ~7× toward sunset to cancel
  the physical sky's dimming; the sunlit deck dims less, so the full gain over-brightened it,
  and below the horizon nothing dimmed its sunlight at all.
- **Fix:** the deck's sunlight × the twilight weight; the clouds take 0.7 of the clear sky's
  make-up (`ATMOSPHERE_CLOUD_MAKEUP`, calibrated: 0.740 / 0.772 / 0.621 against the painted
  0.761 / 0.781 / 0.674); the L5 board test is parametrized by sky.
- **Lesson:** a gate that never ran on a code path proves nothing about it — parametrize the
  existing gates over the new path before adding new ones. And a reviewer's measured fix is a
  hypothesis too: compare it against the reference on the quantity the design promises (here,
  the garden's light), not only on the gate it was measured against.
