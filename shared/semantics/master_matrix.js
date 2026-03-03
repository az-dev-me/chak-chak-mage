// Semantic Matrix containing Interpretations from historia.txt
// Mapped for the GEMINI_3.1_PRO_HIGH album configuration

const masterMatrix = {
    "narrative_phases": [
        {
            "id": "phase_1_discovery",
            "time_range": null, // null means it applies to the whole track unless overridden
            "theme_from_historia": "The discovery of the 'magic box' - The mundane treated as divine. (Tracks 1, 2)",
            "modern_analogy": "The invention of social media, the first smartphone, the promise of connection.",
            "covers_tracks": ["track_01", "track_02"],
            "media_pool": [
                { "type": "image", "url": "bg_t1.png", "weight": 1.0 },
                { "type": "image", "url": "bg_t2.png", "weight": 1.0 }
            ]
        },
        {
            "id": "phase_2_dogma_run",
            "time_range": null,
            "theme_from_historia": "The Genesis of Dogma and the 'Fire Run' - Running frantically with the imaginary flame. (Track 3)",
            "modern_analogy": "The modern Rat Race, Wall Street panic, endless commuting, mindless scrolling.",
            "covers_tracks": ["track_03"],
            "media_pool": [
                { "type": "image", "url": "bg_t3.png", "weight": 1.0 }
            ]
        },
        {
            "id": "phase_3_division",
            "time_range": null,
            "theme_from_historia": "The Rules and Two Fires - Arguing over the color of the box vs the stone. (Tracks 4, 6)",
            "modern_analogy": "Toxic ideological division, boardroom arguments, political polarization.",
            "covers_tracks": ["track_04", "track_06"],
            "media_pool": [
                { "type": "image", "url": "bg_t4.png", "weight": 1.0 }
            ]
        },
        {
            "id": "phase_4_awakening",
            "time_range": null,
            "theme_from_historia": "Muda's Spark - Striking the real stone. (Track 5)",
            "modern_analogy": "Unplugging from the matrix, reading a physical book, finding peace in nature.",
            "covers_tracks": ["track_05"],
            "media_pool": [
                { "type": "image", "url": "bg_t5.png", "weight": 1.0 }
            ]
        },
        {
            "id": "phase_5_collapse",
            "time_range": null,
            "theme_from_historia": "The Empty Lighter - The gas runs out, the illusion breaks. (Tracks 7, 8)",
            "modern_analogy": "Empty consumerism, the loneliness of luxury, staring at a dead screen.",
            "covers_tracks": ["track_07", "track_08"],
            "media_pool": [
                { "type": "image", "url": "bg_t7.png", "weight": 1.0 }
            ]
        },
        {
            "id": "phase_6_epilogue",
            "time_range": null,
            "theme_from_historia": "The Hedgehog - Returning to simple reality. (Track 9)",
            "modern_analogy": "A pet chewing a designer shoe, grounding, the fire was always within reach.",
            "covers_tracks": ["track_09"],
            "media_pool": [
                { "type": "image", "url": "bg_t9.png", "weight": 1.0 }
            ]
        }
    ]
};
