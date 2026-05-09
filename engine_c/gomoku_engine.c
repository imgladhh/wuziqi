#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

#define MAX_SIZE 15
#define MAX_CELLS (MAX_SIZE * MAX_SIZE)
#define MAX_MOVES 64
#define CANDIDATE_LIMIT 14
#define WIN_SCORE 10000000
#define INF_SCORE 2000000000
#define TT_SIZE (1 << 20)

enum {
    EMPTY = 0,
    BLACK = 1,
    WHITE = 2,
    TT_EXACT = 0,
    TT_LOWER = 1,
    TT_UPPER = 2
};

typedef struct {
    int x;
    int y;
    int tier;
    int score;
} MoveC;

typedef struct {
    uint64_t key;
    int score;
    int8_t depth;
    int8_t flag;
    int8_t best_x;
    int8_t best_y;
} TTEntryC;

typedef struct {
    int x[64];
    int y[64];
    int count;
} AffectedCells;

static uint8_t g_cells[MAX_CELLS];
static int g_size = MAX_SIZE;
static int g_move_count = 0;
static uint64_t g_hash = 0;
static uint64_t g_zobrist[MAX_SIZE][MAX_SIZE][3];
static int g_zobrist_ready = 0;
static int g_pat[3][5][3];
static double g_enemy_scale = 1.0;
static double g_start_ms = 0.0;
static double g_time_limit_ms = 1200.0;
static int g_nodes = 0;
static int g_best_x = -1;
static int g_best_y = -1;
static int g_competitive = 0;
static TTEntryC g_tt[TT_SIZE];

static const int DIRS[4][2] = {{1, 0}, {0, 1}, {1, 1}, {1, -1}};

static int idx_xy(int x, int y) {
    return x * g_size + y;
}

static int inside(int x, int y) {
    return x >= 0 && y >= 0 && x < g_size && y < g_size;
}

static int opp(int stone) {
    return stone == BLACK ? WHITE : BLACK;
}

static double now_ms(void) {
    return (double)clock() * 1000.0 / (double)CLOCKS_PER_SEC;
}

static int time_up(void) {
    if (g_time_limit_ms <= 0.0) return 0;
    return (now_ms() - g_start_ms) >= g_time_limit_ms;
}

static uint64_t xorshift64(uint64_t *state) {
    uint64_t x = *state;
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    *state = x;
    return x;
}

static void init_zobrist(void) {
    if (g_zobrist_ready) return;
    uint64_t seed = 0x9e3779b97f4a7c15ULL;
    for (int x = 0; x < MAX_SIZE; x++) {
        for (int y = 0; y < MAX_SIZE; y++) {
            g_zobrist[x][y][EMPTY] = 0;
            g_zobrist[x][y][BLACK] = xorshift64(&seed);
            g_zobrist[x][y][WHITE] = xorshift64(&seed);
        }
    }
    g_zobrist_ready = 1;
}

static int phase_index(void) {
    int cells = g_size * g_size;
    if (g_move_count < (cells * 12) / 100) return 0;
    if (g_move_count <= (cells * 45) / 100) return 1;
    return 2;
}

static int line_score_at(int x, int y, int stone, int phase) {
    if (g_cells[idx_xy(x, y)] != stone) return 0;
    int total = 0;
    for (int d = 0; d < 4; d++) {
        int dx = DIRS[d][0];
        int dy = DIRS[d][1];
        int count = 1;
        int open_ends = 0;
        int lx = x - dx;
        int ly = y - dy;
        while (inside(lx, ly) && g_cells[idx_xy(lx, ly)] == stone) {
            count++;
            lx -= dx;
            ly -= dy;
        }
        if (inside(lx, ly) && g_cells[idx_xy(lx, ly)] == EMPTY) open_ends++;
        int rx = x + dx;
        int ry = y + dy;
        while (inside(rx, ry) && g_cells[idx_xy(rx, ry)] == stone) {
            count++;
            rx += dx;
            ry += dy;
        }
        if (inside(rx, ry) && g_cells[idx_xy(rx, ry)] == EMPTY) open_ends++;
        if (count >= 5) {
            total += WIN_SCORE;
        } else if (count >= 1 && count <= 4 && open_ends >= 0 && open_ends <= 2) {
            total += g_pat[phase][count][open_ends];
        }
    }
    int center = g_size / 2;
    int dist = abs(x - center) + abs(y - center);
    total += (g_size - dist) * 2;
    return total;
}

static void compute_core_scores(int *black_score, int *white_score) {
    int phase = phase_index();
    int b = 0;
    int w = 0;
    for (int x = 0; x < g_size; x++) {
        for (int y = 0; y < g_size; y++) {
            int stone = g_cells[idx_xy(x, y)];
            if (stone == BLACK) {
                b += line_score_at(x, y, BLACK, phase);
            } else if (stone == WHITE) {
                w += line_score_at(x, y, WHITE, phase);
            }
        }
    }
    *black_score = b;
    *white_score = w;
}

static int eval_board(int ai_stone) {
    int cb = 0;
    int cw = 0;
    compute_core_scores(&cb, &cw);
    if (ai_stone == BLACK) {
        return cb - (int)((double)cw * g_enemy_scale);
    }
    return cw - (int)((double)cb * g_enemy_scale);
}

static int eval_from_scores(int ai_stone, int cb, int cw) {
    if (ai_stone == BLACK) {
        return cb - (int)((double)cw * g_enemy_scale);
    }
    return cw - (int)((double)cb * g_enemy_scale);
}

static int eval_for_side_to_move(int ai_stone, int current_stone, int cb, int cw) {
    int value = eval_from_scores(ai_stone, cb, cw);
    return current_stone == ai_stone ? value : -value;
}

static int has_five_from(int x, int y, int stone) {
    for (int d = 0; d < 4; d++) {
        int dx = DIRS[d][0];
        int dy = DIRS[d][1];
        int count = 1;
        int nx = x + dx;
        int ny = y + dy;
        while (inside(nx, ny) && g_cells[idx_xy(nx, ny)] == stone) {
            count++;
            nx += dx;
            ny += dy;
        }
        nx = x - dx;
        ny = y - dy;
        while (inside(nx, ny) && g_cells[idx_xy(nx, ny)] == stone) {
            count++;
            nx -= dx;
            ny -= dy;
        }
        if (count >= 5) return 1;
    }
    return 0;
}

static int has_overline_from(int x, int y, int stone) {
    for (int d = 0; d < 4; d++) {
        int dx = DIRS[d][0];
        int dy = DIRS[d][1];
        int count = 1;
        int nx = x + dx;
        int ny = y + dy;
        while (inside(nx, ny) && g_cells[idx_xy(nx, ny)] == stone) {
            count++;
            nx += dx;
            ny += dy;
        }
        nx = x - dx;
        ny = y - dy;
        while (inside(nx, ny) && g_cells[idx_xy(nx, ny)] == stone) {
            count++;
            nx -= dx;
            ny -= dy;
        }
        if (count >= 6) return 1;
    }
    return 0;
}

static void place_raw(int x, int y, int stone) {
    g_cells[idx_xy(x, y)] = (uint8_t)stone;
    g_hash ^= g_zobrist[x][y][stone];
    g_move_count++;
}

static void remove_raw(int x, int y, int stone) {
    g_move_count--;
    g_hash ^= g_zobrist[x][y][stone];
    g_cells[idx_xy(x, y)] = EMPTY;
}

static int live_four_window_in_direction(int x, int y, int dx, int dy, int stone, int ex, int ey) {
    int px[11];
    int py[11];
    int center = 5;
    for (int offset = -5; offset <= 5; offset++) {
        int i = offset + 5;
        px[i] = x + offset * dx;
        py[i] = y + offset * dy;
    }
    for (int start = 0; start <= 5; start++) {
        int left_x = px[start];
        int left_y = py[start];
        int right_x = px[start + 5];
        int right_y = py[start + 5];
        if (!inside(left_x, left_y) || !inside(right_x, right_y)) continue;
        if (g_cells[idx_xy(left_x, left_y)] != EMPTY || g_cells[idx_xy(right_x, right_y)] != EMPTY) continue;
        if (!(start + 1 <= center && center <= start + 4)) continue;
        int has_extension = (ex < 0 || ey < 0);
        int ok = 1;
        for (int i = start + 1; i <= start + 4; i++) {
            if (!inside(px[i], py[i]) || g_cells[idx_xy(px[i], py[i])] != stone) {
                ok = 0;
                break;
            }
            if (px[i] == ex && py[i] == ey) has_extension = 1;
        }
        if (ok && has_extension) return 1;
    }
    return 0;
}

static int count_live_four_directions(int x, int y, int stone) {
    int total = 0;
    for (int d = 0; d < 4; d++) {
        if (live_four_window_in_direction(x, y, DIRS[d][0], DIRS[d][1], stone, -1, -1)) {
            total++;
        }
    }
    return total;
}

static int open_three_in_direction(int x, int y, int dx, int dy, int stone) {
    for (int offset = -4; offset <= 4; offset++) {
        int ex = x + offset * dx;
        int ey = y + offset * dy;
        if (!inside(ex, ey) || g_cells[idx_xy(ex, ey)] != EMPTY) continue;
        place_raw(ex, ey, stone);
        int is_open_three = 0;
        if (!has_overline_from(ex, ey, stone)) {
            is_open_three = live_four_window_in_direction(x, y, dx, dy, stone, ex, ey);
        }
        remove_raw(ex, ey, stone);
        if (is_open_three) return 1;
    }
    return 0;
}

static int count_open_three_directions(int x, int y, int stone) {
    int total = 0;
    for (int d = 0; d < 4; d++) {
        if (open_three_in_direction(x, y, DIRS[d][0], DIRS[d][1], stone)) {
            total++;
        }
    }
    return total;
}

static int forbidden_type(int x, int y, int stone) {
    if (!g_competitive || stone != BLACK) return 0;
    if (!inside(x, y) || g_cells[idx_xy(x, y)] != EMPTY) return 0;

    place_raw(x, y, stone);
    int result = 0;
    if (has_overline_from(x, y, stone)) {
        result = 1;
    } else if (has_five_from(x, y, stone)) {
        result = 0;
    } else if (count_live_four_directions(x, y, stone) >= 2) {
        result = 2;
    } else if (count_open_three_directions(x, y, stone) >= 2) {
        result = 3;
    }
    remove_raw(x, y, stone);
    return result;
}

static void affected_add(AffectedCells *affected, int x, int y) {
    if (!inside(x, y) || g_cells[idx_xy(x, y)] == EMPTY) return;
    for (int i = 0; i < affected->count; i++) {
        if (affected->x[i] == x && affected->y[i] == y) return;
    }
    if (affected->count >= 64) return;
    affected->x[affected->count] = x;
    affected->y[affected->count] = y;
    affected->count++;
}

static void collect_affected(int x, int y, AffectedCells *affected) {
    affected->count = 0;
    for (int d = 0; d < 4; d++) {
        int dx = DIRS[d][0];
        int dy = DIRS[d][1];
        for (int step = -5; step <= 5; step++) {
            affected_add(affected, x + dx * step, y + dy * step);
        }
    }
}

static void apply_affected_delta(AffectedCells *affected, int phase, int sign, int *cb, int *cw) {
    for (int i = 0; i < affected->count; i++) {
        int x = affected->x[i];
        int y = affected->y[i];
        int stone = g_cells[idx_xy(x, y)];
        if (stone == BLACK) {
            *cb += sign * line_score_at(x, y, BLACK, phase);
        } else if (stone == WHITE) {
            *cw += sign * line_score_at(x, y, WHITE, phase);
        }
    }
}

static int place_incremental(int x, int y, int stone, int *cb, int *cw) {
    int phase_before = phase_index();
    AffectedCells affected;
    collect_affected(x, y, &affected);
    apply_affected_delta(&affected, phase_before, -1, cb, cw);

    place_raw(x, y, stone);
    int winner = has_five_from(x, y, stone) ? stone : EMPTY;
    int phase_after = phase_index();
    if (phase_after != phase_before) {
        compute_core_scores(cb, cw);
        return winner;
    }

    collect_affected(x, y, &affected);
    apply_affected_delta(&affected, phase_after, 1, cb, cw);
    return winner;
}

static void remove_incremental(int x, int y, int stone, int *cb, int *cw) {
    int phase_before = phase_index();
    AffectedCells affected;
    collect_affected(x, y, &affected);
    apply_affected_delta(&affected, phase_before, -1, cb, cw);

    remove_raw(x, y, stone);
    int phase_after = phase_index();
    if (phase_after != phase_before) {
        compute_core_scores(cb, cw);
        return;
    }

    collect_affected(x, y, &affected);
    apply_affected_delta(&affected, phase_after, 1, cb, cw);
}

static int move_pattern_tier(int x, int y, int stone) {
    int enemy = opp(stone);
    place_raw(x, y, stone);
    int own_win = has_five_from(x, y, stone);
    remove_raw(x, y, stone);
    if (own_win) return 0;

    place_raw(x, y, enemy);
    int block_win = has_five_from(x, y, enemy);
    remove_raw(x, y, enemy);
    if (block_win) return 1;

    int phase = phase_index();
    int own_best = 0;
    int enemy_best = 0;
    place_raw(x, y, stone);
    own_best = line_score_at(x, y, stone, phase);
    remove_raw(x, y, stone);
    place_raw(x, y, enemy);
    enemy_best = line_score_at(x, y, enemy, phase);
    remove_raw(x, y, enemy);

    int open_four = g_pat[phase][4][2];
    int half_four = g_pat[phase][4][1];
    int open_three = g_pat[phase][3][2];
    if (own_best >= open_four || enemy_best >= open_four) return 2;
    if (own_best >= half_four || enemy_best >= half_four) return 3;
    if (own_best >= open_three) return 4;
    return 5;
}

static int has_neighbor2(int x, int y) {
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            if (dx == 0 && dy == 0) continue;
            int nx = x + dx;
            int ny = y + dy;
            if (inside(nx, ny) && g_cells[idx_xy(nx, ny)] != EMPTY) return 1;
        }
    }
    return 0;
}

static int gen_candidates(MoveC *moves, int stone, int ply) {
    if (g_move_count == 0) {
        moves[0].x = g_size / 2;
        moves[0].y = g_size / 2;
        moves[0].tier = 0;
        moves[0].score = 100000;
        return 1;
    }
    int min_x = g_size, min_y = g_size, max_x = -1, max_y = -1;
    for (int x = 0; x < g_size; x++) {
        for (int y = 0; y < g_size; y++) {
            if (g_cells[idx_xy(x, y)] != EMPTY) {
                if (x < min_x) min_x = x;
                if (y < min_y) min_y = y;
                if (x > max_x) max_x = x;
                if (y > max_y) max_y = y;
            }
        }
    }
    min_x -= 2; min_y -= 2; max_x += 2; max_y += 2;
    if (min_x < 0) min_x = 0;
    if (min_y < 0) min_y = 0;
    if (max_x >= g_size) max_x = g_size - 1;
    if (max_y >= g_size) max_y = g_size - 1;

    int count = 0;
    int center = g_size / 2;
    for (int x = min_x; x <= max_x; x++) {
        for (int y = min_y; y <= max_y; y++) {
            if (g_cells[idx_xy(x, y)] != EMPTY || !has_neighbor2(x, y)) continue;
            MoveC m;
            m.x = x;
            m.y = y;
            m.tier = move_pattern_tier(x, y, stone);
            int dist = abs(x - center) + abs(y - center);
            m.score = (5 - m.tier) * 100000 - dist * 8 + (ply < 8 ? (center * 2 - dist) : 0);
            if (count < MAX_MOVES) {
                moves[count++] = m;
            }
        }
    }
    for (int i = 1; i < count; i++) {
        MoveC key = moves[i];
        int j = i - 1;
        while (j >= 0 && (moves[j].tier > key.tier || (moves[j].tier == key.tier && moves[j].score < key.score))) {
            moves[j + 1] = moves[j];
            j--;
        }
        moves[j + 1] = key;
    }
    if (g_competitive && stone == BLACK) {
        int filtered = 0;
        for (int i = 0; i < count; i++) {
            if (forbidden_type(moves[i].x, moves[i].y, BLACK) == 0) {
                moves[filtered++] = moves[i];
            }
        }
        count = filtered;
    }
    if (count > CANDIDATE_LIMIT) count = CANDIDATE_LIMIT;
    return count;
}

static int tt_probe(uint64_t key, int depth, int *alpha, int *beta, int *out_score) {
    TTEntryC *entry = &g_tt[key & (TT_SIZE - 1)];
    if (entry->key != key || entry->depth < depth) return 0;
    int score = entry->score;
    if (entry->flag == TT_EXACT) {
        *out_score = score;
        return 1;
    }
    if (entry->flag == TT_LOWER && score > *alpha) *alpha = score;
    if (entry->flag == TT_UPPER && score < *beta) *beta = score;
    if (*alpha >= *beta) {
        *out_score = score;
        return 1;
    }
    return 0;
}

static void tt_store(uint64_t key, int depth, int score, int alpha_orig, int beta_orig, int best_x, int best_y) {
    TTEntryC *entry = &g_tt[key & (TT_SIZE - 1)];
    entry->key = key;
    entry->score = score;
    entry->depth = (int8_t)depth;
    if (score <= alpha_orig) entry->flag = TT_UPPER;
    else if (score >= beta_orig) entry->flag = TT_LOWER;
    else entry->flag = TT_EXACT;
    entry->best_x = (int8_t)best_x;
    entry->best_y = (int8_t)best_y;
}

static int negamax(int depth, int alpha, int beta, int ai_stone, int current_stone, int ply, int cb, int cw) {
    if (time_up()) return eval_for_side_to_move(ai_stone, current_stone, cb, cw);
    g_nodes++;
    if (depth <= 0 || g_move_count >= g_size * g_size) return eval_for_side_to_move(ai_stone, current_stone, cb, cw);

    int alpha_orig = alpha;
    int beta_orig = beta;
    uint64_t key = g_hash ^ ((uint64_t)current_stone * 0x9e3779b97f4a7c15ULL);
    int cached = 0;
    if (tt_probe(key, depth, &alpha, &beta, &cached)) return cached;

    MoveC moves[MAX_MOVES];
    int move_count = gen_candidates(moves, current_stone, ply);
    if (move_count <= 0) return eval_for_side_to_move(ai_stone, current_stone, cb, cw);

    int best_score = -INF_SCORE;
    int best_x = moves[0].x;
    int best_y = moves[0].y;
    int enemy = opp(current_stone);

    for (int i = 0; i < move_count; i++) {
        MoveC m = moves[i];
        int child_cb = cb;
        int child_cw = cw;
        int winner = place_incremental(m.x, m.y, current_stone, &child_cb, &child_cw);
        int score;
        if (winner == current_stone) {
            score = WIN_SCORE - ply;
        } else {
            int next_depth = depth - 1;
            int reduced = depth >= 3 && i >= 4 && m.tier >= 4 && next_depth >= 2;
            int search_depth = reduced ? next_depth - 1 : next_depth;
            if (i == 0) {
                score = -negamax(search_depth, -beta, -alpha, ai_stone, enemy, ply + 1, child_cb, child_cw);
            } else {
                score = -negamax(search_depth, -alpha - 1, -alpha, ai_stone, enemy, ply + 1, child_cb, child_cw);
                if (reduced && score > alpha) {
                    score = -negamax(next_depth, -alpha - 1, -alpha, ai_stone, enemy, ply + 1, child_cb, child_cw);
                }
                if (score > alpha && score < beta) {
                    score = -negamax(next_depth, -beta, -alpha, ai_stone, enemy, ply + 1, child_cb, child_cw);
                }
            }
        }
        remove_incremental(m.x, m.y, current_stone, &child_cb, &child_cw);

        if (score > best_score) {
            best_score = score;
            best_x = m.x;
            best_y = m.y;
        }
        if (score > alpha) alpha = score;
        if (alpha >= beta) break;
        if (time_up()) break;
    }
    tt_store(key, depth, best_score, alpha_orig, beta_orig, best_x, best_y);
    return best_score;
}

static int find_immediate_win(int stone, int *out_x, int *out_y) {
    MoveC moves[MAX_MOVES];
    int count = gen_candidates(moves, stone, 0);
    for (int i = 0; i < count; i++) {
        MoveC m = moves[i];
        place_raw(m.x, m.y, stone);
        int wins = has_five_from(m.x, m.y, stone);
        remove_raw(m.x, m.y, stone);
        if (wins) {
            *out_x = m.x;
            *out_y = m.y;
            return 1;
        }
    }
    return 0;
}

static int search_root(int depth, int ai_stone, int cb0, int cw0) {
    MoveC moves[MAX_MOVES];
    int move_count = gen_candidates(moves, ai_stone, 0);
    int best_score = -INF_SCORE;
    int best_x = -1;
    int best_y = -1;
    int enemy = opp(ai_stone);
    int alpha = -INF_SCORE + 1;
    int beta = INF_SCORE - 1;

    for (int i = 0; i < move_count; i++) {
        MoveC m = moves[i];
        int child_cb = cb0;
        int child_cw = cw0;
        int winner = place_incremental(m.x, m.y, ai_stone, &child_cb, &child_cw);
        int score;
        if (winner == ai_stone) {
            score = WIN_SCORE;
        } else if (i == 0) {
            score = -negamax(depth - 1, -beta, -alpha, ai_stone, enemy, 1, child_cb, child_cw);
        } else {
            score = -negamax(depth - 1, -alpha - 1, -alpha, ai_stone, enemy, 1, child_cb, child_cw);
            if (score > alpha && score < beta) {
                score = -negamax(depth - 1, -beta, -alpha, ai_stone, enemy, 1, child_cb, child_cw);
            }
        }
        remove_incremental(m.x, m.y, ai_stone, &child_cb, &child_cw);
        if (score > best_score) {
            best_score = score;
            best_x = m.x;
            best_y = m.y;
        }
        if (score > alpha) alpha = score;
        if (time_up()) break;
    }
    if (best_x >= 0) {
        g_best_x = best_x;
        g_best_y = best_y;
    }
    return best_score;
}

static void init_patterns(int open_four, int half_four, int open_three, int half_three, int open_two, int half_two) {
    memset(g_pat, 0, sizeof(g_pat));
    for (int p = 0; p < 3; p++) {
        g_pat[p][1][0] = 10;
        g_pat[p][1][1] = 10;
        g_pat[p][1][2] = p == 0 ? 100 : (p == 1 ? 90 : 70);
        g_pat[p][2][2] = p == 0 ? 1600 : (p == 1 ? open_two : 1200);
        g_pat[p][2][1] = p == 0 ? 360 : (p == 1 ? half_two : 320);
        g_pat[p][3][2] = p == 0 ? 22000 : (p == 1 ? open_three : 20000);
        g_pat[p][3][1] = p == 0 ? 4500 : (p == 1 ? half_three : 5400);
        g_pat[p][4][2] = p == 0 ? 180000 : (p == 1 ? open_four : 280000);
        g_pat[p][4][1] = p == 0 ? 45000 : (p == 1 ? half_four : 75000);
    }
}

EXPORT int c_best_move(
    const uint8_t *board,
    int size,
    int stone,
    int move_count,
    int depth,
    double time_limit_ms,
    int score_open_four,
    int score_half_four,
    int score_open_three,
    int score_half_three,
    int score_open_two,
    int score_half_two,
    double enemy_scale,
    int competitive,
    int *out_x,
    int *out_y
) {
    init_zobrist();
    if (size <= 0 || size > MAX_SIZE || (stone != BLACK && stone != WHITE)) {
        *out_x = -1;
        *out_y = -1;
        return 0;
    }
    g_size = size;
    g_move_count = 0;
    g_hash = 0;
    g_nodes = 0;
    g_best_x = -1;
    g_best_y = -1;
    g_competitive = competitive ? 1 : 0;
    g_time_limit_ms = time_limit_ms;
    g_start_ms = now_ms();
    g_enemy_scale = enemy_scale;
    init_patterns(score_open_four, score_half_four, score_open_three, score_half_three, score_open_two, score_half_two);
    memset(g_tt, 0, sizeof(g_tt));
    memset(g_cells, 0, sizeof(g_cells));

    int seen_moves = 0;
    for (int x = 0; x < size; x++) {
        for (int y = 0; y < size; y++) {
            int value = board[x * size + y];
            if (value == BLACK || value == WHITE) {
                g_cells[idx_xy(x, y)] = (uint8_t)value;
                g_hash ^= g_zobrist[x][y][value];
                seen_moves++;
            }
        }
    }
    g_move_count = move_count >= 0 ? move_count : seen_moves;

    int x = -1;
    int y = -1;
    if (find_immediate_win(stone, &x, &y) || find_immediate_win(opp(stone), &x, &y)) {
        *out_x = x;
        *out_y = y;
        return 1;
    }

    int cb0 = 0;
    int cw0 = 0;
    compute_core_scores(&cb0, &cw0);

    if (depth < 1) depth = 1;
    int last_x = -1;
    int last_y = -1;
    for (int d = 1; d <= depth; d++) {
        int before_x = g_best_x;
        int before_y = g_best_y;
        search_root(d, stone, cb0, cw0);
        if (time_up()) {
            if (last_x >= 0) {
                g_best_x = last_x;
                g_best_y = last_y;
            } else {
                g_best_x = before_x;
                g_best_y = before_y;
            }
            break;
        }
        if (g_best_x >= 0) {
            last_x = g_best_x;
            last_y = g_best_y;
        }
    }

    if (g_best_x < 0 || g_best_y < 0) {
        MoveC moves[MAX_MOVES];
        int count = gen_candidates(moves, stone, 0);
        if (count > 0) {
            g_best_x = moves[0].x;
            g_best_y = moves[0].y;
        }
    }
    *out_x = g_best_x;
    *out_y = g_best_y;
    return g_best_x >= 0 && g_best_y >= 0;
}

EXPORT int c_last_nodes(void) {
    return g_nodes;
}
