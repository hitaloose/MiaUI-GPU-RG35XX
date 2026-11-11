#ifndef __RA_SOFTCORE_H__
#define __RA_SOFTCORE_H__

// [softcore] Fork-only: see common/softcore.h. RA_* are implemented in
// ra_softcore.inc, which ra_offline.c includes at its end; the rest is
// minarch's side, kept here so minarch.c only carries one-line hooks.

#include "softcore.h"

// Before RA_loadGame (after RA_init is fine: this isn't part of its context).
// Softcore keeps its unlocks in <root>/softcore/ so NekoBit never sees them.
void RA_setSoftcore(int enabled);
// 1 while the loaded game is in Softcore (0 when nothing is loaded).
int RA_isSoftcore(void);

// FE_OPT_ACHIEVEMENTS, per game. 0 and 1 are upstream's Off and On, so a
// config saved before the modes keeps working: On now follows the global mode.
enum { SC_GAME_OFF, SC_GAME_GLOBAL, SC_GAME_HARDCORE, SC_GAME_SOFTCORE, SC_GAME_COUNT };
static char* SC_game_values[] = {"Off", "On", "Hardcore", "Softcore", NULL}; // what the .cfg stores
static char* SC_game_labels[SC_GAME_COUNT + 1]; // what the menu shows, see SC_localize

static inline void SC_localize(void) {
    SC_game_labels[SC_GAME_OFF] = (char*)T(STR_QM_OFF);
    SC_game_labels[SC_GAME_GLOBAL] = (char*)T(STR_MA_ACH_GLOBAL);
    SC_game_labels[SC_GAME_HARDCORE] = (char*)T(STR_QM_RA_HARDCORE);
    SC_game_labels[SC_GAME_SOFTCORE] = (char*)T(STR_QM_RA_SOFTCORE);
}

static inline int SC_gameSoftcore(int game_value) {
    return game_value == SC_GAME_SOFTCORE || (game_value == SC_GAME_GLOBAL && SC_globalSoftcore());
}

#endif
