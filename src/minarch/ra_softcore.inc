// [softcore] Fork-only, included at the end of ra_offline.c so it can reach
// that file's statics without upstream's code having to change. See
// ra_softcore.h and common/softcore.h.
//
// Softcore keeps its own progress file, same format and tamper check:
//
//   <root>/softcore/<TAG>/<hash>_progress.json
//
// NekoBit only reads <root>/progress/, so nothing earned here pays XP, moves a
// mission or counts for a mastery. What's earned in Hardcore is folded in
// when the game loads, so it shows as unlocked and doesn't fire again; the
// other way round it stays locked, and earning it in Hardcore later pays.
// Only the softcore file is ever written in this mode (an unlock, a wipe).

// ra_softcore and ra_sc_loadProgress are declared near the top of ra_offline.c

void RA_setSoftcore(int enabled) {
    ra_softcore = enabled ? 1 : 0;
}

int RA_isSoftcore(void) {
    return ra.active && ra_softcore;
}

static void ra_sc_loadProgress(const char* emu_tag) {
    // 1. Hardcore's file, exactly as upstream reads it (ra.progress_path, the
    // arcade adoption already done by the caller)
    ra_loadProgress();

    uint32_t hc_count = ra.unlocked_count;
    RA_Unlock* hc = NULL;
    if (hc_count) {
        hc = malloc(hc_count * sizeof(RA_Unlock));
        if (hc) memcpy(hc, ra.unlocked, hc_count * sizeof(RA_Unlock));
        else hc_count = 0;
    }

    // 2. from here on ra.progress_path is the softcore file: every save, the
    // unlock handler's and RA_wipeProgress' included, goes there
    char dir[MAX_PATH];
    snprintf(dir, sizeof(dir), "%s/softcore", ra.root);
    mkdir(dir, 0755);
    snprintf(dir, sizeof(dir), "%s/softcore/%s", ra.root, emu_tag);
    mkdir(dir, 0755);
    snprintf(ra.progress_path, sizeof(ra.progress_path), "%s/%s_progress.json", dir, ra.hash);

    // 3. the softcore file on its own, so its checksum checks out
    ra.unlocked_count = 0;
    ra.invalidated = 0;
    ra.progress_stale = 0;
    ra_loadProgress();

    // 4. Hardcore's unlocks on top
    uint32_t before = ra.unlocked_count;
    for (uint32_t i=0; i<hc_count; i++) ra_addUnlocked(hc[i].id, hc[i].date);
    if (ra.unlocked_count!=before) ra.progress_stale = 1;
    free(hc);

    LOG_info("RA: softcore, %u unlocked (%u from hardcore)\n", ra.unlocked_count, hc_count);
}
