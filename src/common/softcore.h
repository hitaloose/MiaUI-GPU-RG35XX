#ifndef __SOFTCORE_H__
#define __SOFTCORE_H__

// [softcore] Fork-only: achievements Off / Hardcore / Softcore.
//
// Hardcore is upstream's "On": no save states. Softcore allows them, and what
// it unlocks goes to RETROACHIVEMENTS_PATH/softcore/ instead of progress/, so
// NekoBit (which only reads progress/) never counts it.
//
// The global mode is msettings' RA switch plus a flag file: no file means
// Hardcore, so a card without it behaves like upstream. Shared by minui (the
// Quick Menu sets it) and minarch (reads it at launch). Header only.

#include <stdio.h>
#include <unistd.h>
#include <msettings.h>
#include "defines.h"
#include "i18n.h"

#define RA_SOFTCORE_PATH SHARED_USERDATA_PATH "/ra-softcore"

enum { SC_MODE_OFF, SC_MODE_HARDCORE, SC_MODE_SOFTCORE, SC_MODE_COUNT };

static inline int SC_globalSoftcore(void) {
    return access(RA_SOFTCORE_PATH, F_OK) == 0;
}

static inline int SC_raMode(void) {
    if (!GetRAEnabled()) return SC_MODE_OFF;
    return SC_globalSoftcore() ? SC_MODE_SOFTCORE : SC_MODE_HARDCORE;
}

static inline void SC_setRaMode(int mode) {
    SetRAEnabled(mode != SC_MODE_OFF);
    if (mode == SC_MODE_SOFTCORE) {
        FILE* f = fopen(RA_SOFTCORE_PATH, "w");
        if (f) fclose(f);
    }
    else unlink(RA_SOFTCORE_PATH);
}

static inline int SC_modeLabel(int mode) {
    static const int ids[SC_MODE_COUNT] = {STR_QM_OFF, STR_QM_RA_HARDCORE, STR_QM_RA_SOFTCORE};
    return ids[mode];
}

#endif
