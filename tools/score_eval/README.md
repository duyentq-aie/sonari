# score_eval

Native calibration (`make score-native`) and Part 2, the Vietnamese evaluation set:
`make score-vi DUMP=<dir> NOTES=<file>`. `DUMP` is what the speech service wrote with
`SPEECH_DEBUG_DUMP_DIR` set; `NOTES` you write by hand while recording. Keep both outside the repo
and never commit them (a person's voice). Each recording is scored again from its audio under
thresholds v1 and v2; the saved response is ignored.

## Notes format

One line per recording, in recording order; blank lines and text after `#` are ignored.

    normal                     # read the sentence as well as you can
    error think θ              # said "tink": the word, then the phoneme you changed

The phoneme is the expected one as `/v1/score` names it (`expected`, espeak IPA: `θ ð s z ɪ iː`...);
the word is the first in the sentence with that spelling. The run stops when the notes and the
recordings differ in number, or a note names a word or phoneme the sentence lacks: a retake shifts
every later line, so fix the notes (or delete the extra recording directory) first.

## Report and verdict

Per version: deliberate errors marked wrong, and other wrongs in those recordings; for normal
readings wrong / unclear / correct, called deviations (the speaker is a learner, so a wrong may be
real); whole-word failures (2+ phonemes, most wrong: collapse or a real breakdown, listen); and
recordings the scorer refused. The verdict on v2 follows a rule fixed before any recording: **fit to
show a learner** when at least 80% of deliberate errors are marked wrong and normal readings average
at most 1.0 wrong phoneme; without both kinds of recording, cannot tell. Revisit the rule freely.
