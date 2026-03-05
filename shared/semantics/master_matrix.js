// Semantic Matrix — Narrative Phase Mapping from historia.txt
// Maps 6 narrative phases across 9 tracks with dual-layer visual narratives.
//
// LITERAL LAYER (media_queries → Zone 1 + Zone 3):
//   Prehistoric allegory — cavemen, fire, orange box/lighter, Gralha, Muda, tribal split
//
// HIDDEN LAYER (hidden_media_queries → Zone 2 outer modals):
//   Modern parallel — tech worship, hustle culture, polarization, open source, collapse, reflection

const masterMatrix = {
    "narrative_phases": [
        {
            "id": "phase_1_discovery",
            "theme_from_historia": "The Arrival — A time traveler lands among cave dwellers with a BIC lighter. The mundane becomes divine.",
            "modern_parallel": "First encounter with technology: a teenager discovers the internet, the first iPhone unboxing, Silicon Valley wonder.",
            "literal_arc": "Green phone booth → prehistoric valley → meeting Gralha → the chak-chak moment → instant worship",
            "hidden_arc": "Dusty laptop in attic → first screen glow → tech influencer profile → Apple keynote → product as prayer",
            "covers_tracks": ["track_01", "track_02"],
            "line_counts": { "track_01": 31, "track_02": 25 }
        },
        {
            "id": "phase_2_the_fire_run",
            "theme_from_historia": "The Fire Run — Gralha runs with the flame, the tribe cheers, arbitrary rules form. The ritual of running becomes sacred.",
            "modern_parallel": "The daily hustle: 5:30am alarm → commute → startup grind → burnout → self-help dogma → same alarm Monday.",
            "literal_arc": "Dawn flame → running with torch → wind in face → flame dies → rules invented → Tronco worships the wheel → repeat",
            "hidden_arc": "Monday alarm → subway sprint → Slack floods → burnout at desk → self-help gurus → crypto worship → same loop",
            "covers_tracks": ["track_03"],
            "line_counts": { "track_03": 21 }
        },
        {
            "id": "phase_3_the_rules",
            "theme_from_historia": "The Rules — Tribe fractures into factions. Arguments, holy writ, dogma. Tronco prays to the toothed wheel. The Mage sits detached on his throne.",
            "modern_parallel": "Political polarization: cable news split screens, echo chambers, Twitter wars, corporate compliance, lost youth.",
            "literal_arc": "Tribe splits → factions argue → rules ritualized → youth reject → Mage alone on throne → box becomes sacred",
            "hidden_arc": "Family dinner fight → Fox vs MSNBC → compliance training → Gen-Z TikTok mocking → CEO in jet → Times Square cathedral",
            "covers_tracks": ["track_04"],
            "line_counts": { "track_04": 23 }
        },
        {
            "id": "phase_4_mudas_spark",
            "theme_from_historia": "Muda's Spark — The silent observer picks up a stone, strikes it, creates fire without running. The open-source revolution.",
            "modern_parallel": "Free knowledge: library → Linux manual → Hello World → Wikipedia → open source → teaching patiently → fire was always ours.",
            "literal_arc": "Muda watches → picks up stone → tchak tchak → fire! → teaches slowly → Gralha's jaw drops → even liberation becomes dogma",
            "hidden_arc": "Quiet student → first code → Wikipedia edit → GitHub → repair cafe → VC asks 'how monetize?' → open source co-opted",
            "covers_tracks": ["track_05"],
            "line_counts": { "track_05": 25 }
        },
        {
            "id": "phase_5_two_fires",
            "theme_from_historia": "Two Fires — Gralhistas vs Mudistas. The great schism. Tronco paralyzed in the middle. 'I'm just scared of the dark.'",
            "modern_parallel": "Culture war: partisan media, cancel culture, tribal chanting, dueling protests, fear as the engine of all -isms.",
            "literal_arc": "Box is law → Muda's wrong → TWO FIRES → GRAL-HA vs MU-DA → Tronco frozen → same night same fear → Where's the Mage?",
            "hidden_arc": "Terms of Service → cancel mob → split-screen news → sports tribal → moderate ignored → scared of dark → CEO gone",
            "covers_tracks": ["track_06"],
            "line_counts": { "track_06": 23 }
        },
        {
            "id": "phase_6_collapse_and_escape",
            "theme_from_historia": "The Empty Lighter — Gas runs out, Mage escapes with hedgehog Revolution. The tribe fights over an empty shell.",
            "modern_parallel": "The crash: CEO exits, IPO to bust, e-waste mountains, Black Friday stampede for nothing, logging off, 'I'll call you Revolution.'",
            "literal_arc": "Slipped away → threw lighter → tribe fought for empty plastic → ran to green cell → grabbed hedgehog → named Revolution",
            "hidden_arc": "Box of belongings → IPO bell → FOMO buying → dead screen → e-waste dump → delete apps → journal by candlelight",
            "covers_tracks": ["track_07"],
            "line_counts": { "track_07": 21 }
        },
        {
            "id": "phase_7_reflection",
            "theme_from_historia": "The Fire Was Always There — Back on the couch with Revolution. Nothing has changed. The stone is still on the ground, waiting.",
            "modern_parallel": "The devastating mirror: caveman = commuter, campfire = phone screen, tribal chant = brand slogan. THE STONE IS THERE.",
            "literal_arc": "Couch → hedgehog → lighter was just a lighter → running with dying flame → stone upon the ground → fire still there → waiting",
            "hidden_arc": "Phone face-down → dog chews VR headset → cave painting = Instagram → morning commute = fire run → wildflower in concrete → waiting",
            "covers_tracks": ["track_08"],
            "line_counts": { "track_08": 19 }
        },
        {
            "id": "phase_8_epilogue",
            "theme_from_historia": "The Final Message — The lighter was just a lighter. Nothing has changed. The fire is still there. Waiting for someone to strike the stone.",
            "modern_parallel": "Full circle: same apartment, same loop, but the stone is still at your feet. Put the phone down. Pick up the rock. Chak-chak.",
            "literal_arc": "Home → same shit → tool became totem → nothing changed → fire waiting → strike the stone",
            "hidden_arc": "Phone untouched → same news loop → museum of phones → child strikes rocks on beach → two hands meeting, no phones between them",
            "covers_tracks": ["track_09"],
            "line_counts": { "track_09": 9 }
        }
    ]
};
