// =============================================================================
//  ESP32 Screwdriver Antenna Tuner — 3D-printed enclosure (parametric)
//  Two parts: base tray (PCB + rear panel connectors) and lid (control panel).
//  Units: mm.  Render one part at a time with the `part` selector below.
//
//  The board is 100 x 70 mm with M3 mounting holes at (4.5,4.5) (95.5,4.5)
//  (4.5,65.5) (95.5,65.5) — these match gen_pcb.py HOLES exactly.
//
//  Cutout positions are derived from the PCB component placement (KiCad coords,
//  origin top-left, Y down).  All are parameters — nudge to match the exact
//  parts you mount.  Print base + lid in PETG (cab heat) or PLA for bench use.
// =============================================================================

part = "both";          // "base" | "lid" | "both" | "assembled" | "assembled_clear" | "lid_off" | "service_open"
view_rot = [0, 0, 0];    // rotate whole preview for render angles
$fn  = 64;

// ---- board & fit ------------------------------------------------------------
board_l   = 100;        // X
board_w   = 70;         // Y
board_t   = 1.6;
gap       = 2;          // clearance board edge -> inner wall
wall      = 3;          // side wall thickness
floor_t   = 3;          // base floor thickness
lid_t     = 3;          // lid plate thickness
standoff_h= 6;          // PCB underside above floor (room for through-hole tails)
comp_clear= 20;         // headroom above board (DevKit on header + OLED ~ tallest)

// ---- derived ----------------------------------------------------------------
inner_l = board_l + 2*gap;          // 104
inner_w = board_w + 2*gap;          // 74
outer_l = inner_l + 2*wall;         // 110
outer_w = inner_w + 2*wall;         // 80
cav_h   = standoff_h + board_t + comp_clear;   // inner cavity height (27.6)
rim_z   = floor_t + cav_h;          // top of walls
board_z = floor_t + standoff_h;     // board underside Z
board_top = board_z + board_t;
show_board_preview = true;

// board(bx,by) -> enclosure(x,y).  Y is kept (KiCad Y-down == our Y from rear).
function be(bx,by) = [wall+gap+bx, wall+gap+by];

holes = [[4.5,4.5],[95.5,4.5],[4.5,65.5],[95.5,65.5]];   // board coords

// ---- enclosure RF connector sizing -----------------------------------------
// Project standard is Mini-UHF bulkheads for compact enclosure footprint.
rf_bulkhead_pn = "Amphenol RF 172147";
rf_bulkhead_d = 10.0;
rf_mount_holes = false;          // 172147 is a threaded bushing + nut style
rf_mount_hole_d = 3.2;           // M3 clearance
rf_mount_hole_pitch = 14.0;      // center-to-center spacing, adjust to hardware

// ---- rear-panel (Y-min wall) connectors: [x_center, diameter] ---------------
// Panel-mount, wired to the board headers by flying leads.
rear_round = [
  [ 20, rf_bulkhead_d],   // RF IN bulkhead (J3)
  [ 44, rf_bulkhead_d],   // RF OUT bulkhead (J4)
  [ 68, 16.0],   // GX16 radio bulkhead (J2 universal)
  [ 92, 12.0],   // 12V power panel jack (J1)
];
rear_z    = floor_t + 11;   // connector centre height above floor
// ---- right side wall (X-max) extras ----------------------------------------
side_round = [ [30, 6.5] ];     // ext-SWR 3.5mm jack (J5), [y_center, dia]
motor_bulkhead_y = 55;
motor_bulkhead_d = 16.0;        // detachable antenna connector (GX16-4 style)

// ---- lid control-panel cutouts (ergonomic layout; enclosure coords) ---------
// PANEL-MOUNTED UI wired by flying lead to the board headers (J_OLED, SW1 TUNE,
// SW2 PARK, J_TUNE jog). Pure auto-tuner: no encoder, no mode switch.
oled_c    = [45, 26];  oled_win  = [30, 17];   // SSD1306 active-area window
btn_xy    = [[30,66], [50,66]];  btn_d = 6;    // TUNE / PARK buttons
jog_c     = [88, 66];  jog_slot  = [13, 9];    // jog rocker

// =============================================================================

module screw_pilot(d=2.6, h=12) cylinder(d=d, h=h);   // M3 self-tap pilot

// 4 PCB standoffs on the floor; board screwed down from above
module standoffs() {
  for (h = holes) {
    p = be(h[0], h[1]);
    translate([p[0], p[1], floor_t]) difference() {
      cylinder(d=6, h=standoff_h);
      translate([0,0,-0.1]) screw_pilot(2.6, standoff_h+0.2);
    }
  }
}

// 4 lid-screw bosses hanging from the top of the walls (above the board, so the
// board can still drop in).  Lid screws down into these.
lid_boss = [[12, wall], [outer_l-12, wall],
            [12, outer_w-wall], [outer_l-12, outer_w-wall]];
module lid_bosses() {
  for (b = lid_boss)
    translate([b[0], b[1], rim_z-12]) difference() {
      cylinder(d=7, h=12);
      translate([0,0,2]) screw_pilot(2.6, 11);
    }
}

module base() {
  difference() {
    union() {
      // hollow shell (open top)
      difference() {
        cube([outer_l, outer_w, rim_z]);
        translate([wall, wall, floor_t]) cube([inner_l, inner_w, cav_h+1]);
      }
      standoffs();
      lid_bosses();
    }
    // rear-wall round cutouts (bored along +Y through the Y-min wall)
    for (c = rear_round)
      translate([c[0], -1, rear_z]) rotate([-90,0,0]) cylinder(d=c[1], h=wall+2);
    // optional flange screw holes for RF bulkheads (first two rear cutouts)
    if (rf_mount_holes) {
      for (cx = [rear_round[0][0], rear_round[1][0]]) {
        for (sx = [-1, 1])
          translate([cx + sx*(rf_mount_hole_pitch/2), -1, rear_z])
            rotate([-90,0,0]) cylinder(d=rf_mount_hole_d, h=wall+2);
      }
    }
    // right side wall (X-max): ext-SWR jack + cable slot, bored along +X
    for (c = side_round)
      translate([outer_l-wall-1, c[0], rear_z]) rotate([0,90,0]) cylinder(d=c[1], h=wall+2);
    // detachable antenna connector hole on side wall (J6 harness)
    translate([outer_l-wall-1, motor_bulkhead_y, rear_z]) rotate([0,90,0]) cylinder(d=motor_bulkhead_d, h=wall+2);
    // vent slots on the left (X-min) side wall
    for (sy = [20:12:60]) for (sz = [0,1])
      translate([-1, sy, floor_t+5+sz*8]) cube([wall+2, 8, 1.6]);
  }
}

module lid() {
  difference() {
    union() {
      cube([outer_l, outer_w, lid_t]);
      // locating lip that drops into the cavity (inset to clear lid bosses)
      translate([wall+4, wall+4, -4])
        cube([inner_l-8, inner_w-8, 4]);
    }
    // lid screw clearance holes + counterbores
    for (b = lid_boss) translate([b[0], b[1], -0.1]) {
      cylinder(d=3.4, h=lid_t+0.2);
      translate([0,0,lid_t-1.6]) cylinder(d=6.2, h=2);
    }
    // ---- control-panel cutouts ----
    translate([oled_c[0]-oled_win[0]/2, oled_c[1]-oled_win[1]/2, -1])
      cube([oled_win[0], oled_win[1], lid_t+2]);
    for (b = btn_xy) translate([b[0], b[1], -1]) cylinder(d=btn_d, h=lid_t+2);
    translate([jog_c[0]-jog_slot[0]/2, jog_c[1]-jog_slot[1]/2, -1])
      cube([jog_slot[0], jog_slot[1], lid_t+2]);
  }
}

module panel_connectors_preview() {
  // Rear-panel connectors (outside the enclosure).
  for (i = [0:1]) {
    x = rear_round[i][0];
    color([0.75, 0.75, 0.78]) translate([x, -9, rear_z]) rotate([-90,0,0]) cylinder(d=12, h=8);
    color([0.62, 0.62, 0.66]) translate([x, -2.2, rear_z]) rotate([-90,0,0]) cylinder(d=14, h=2);
  }
  color([0.75, 0.75, 0.78]) translate([rear_round[2][0], -9, rear_z]) rotate([-90,0,0]) cylinder(d=16, h=8); // radio GX16
  color([0.62, 0.62, 0.66]) translate([rear_round[3][0], -8, rear_z]) rotate([-90,0,0]) cylinder(d=12, h=7); // power jack

  // Side connectors (outside right wall).
  color([0.75, 0.75, 0.78]) translate([outer_l+7, side_round[0][0], rear_z]) rotate([0,90,0]) cylinder(d=6.5, h=7); // ext SWR
  color([0.75, 0.75, 0.78]) translate([outer_l+8, motor_bulkhead_y, rear_z]) rotate([0,90,0]) cylinder(d=16, h=8);   // antenna bulkhead
}

module coax_pigtails_preview() {
  // Short RG-316 style pigtails from rear RF bulkheads to board edge.
  wire_path([[rear_round[0][0], -2.5, rear_z], [rear_round[0][0], 4, rear_z+1], [wall+gap+10, wall+gap+2, board_top+1]], 1.5, [0.7, 0.7, 0.72]);
  wire_path([[rear_round[1][0], -2.5, rear_z], [rear_round[1][0], 4, rear_z+1], [wall+gap+25, wall+gap+2, board_top+1]], 1.5, [0.7, 0.7, 0.72]);
}

module lid_panel_parts(lid_pos=[0, 0, 0]) {
  translate(lid_pos) {
    // OLED module and glass on lid top.
    color([0.06, 0.06, 0.06])
      translate([oled_c[0]-19, oled_c[1]-13, lid_t]) cube([38, 26, 6]);
    color([0.1, 0.22, 0.65])
      translate([oled_c[0]-15, oled_c[1]-8.5, lid_t+6]) cube([30, 17, 1]);

    // TUNE/PARK button caps.
    color([0.25, 0.85, 0.25]) translate([btn_xy[0][0], btn_xy[0][1], lid_t]) cylinder(d=8, h=5); // TUNE
    color([0.22, 0.22, 0.22]) translate([btn_xy[1][0], btn_xy[1][1], lid_t]) cylinder(d=8, h=5); // PARK

    // Jog rocker cap.
    color([0.95, 0.55, 0.1])
      translate([jog_c[0]-8, jog_c[1]-5, lid_t]) cube([16, 10, 4]);
  }
}

module wire_segment(p1, p2, d=1.0) {
  hull() {
    translate(p1) sphere(d=d);
    translate(p2) sphere(d=d);
  }
}

module wire_path(points, d=1.0, col=[0.85, 0.2, 0.2]) {
  color(col)
    for (i = [0 : len(points)-2])
      wire_segment(points[i], points[i+1], d);
}

module service_wiring(lid_pos=[0,0,0], slack=24) {
  // Board-side anchor points near J_OLED / SW1 / SW2 / J_TUNE headers.
  p_oled = [wall+gap+88, wall+gap+60, board_top+2.5];
  p_sw1  = [wall+gap+88, wall+gap+53, board_top+2.5];
  p_sw2  = [wall+gap+88, wall+gap+46, board_top+2.5];
  p_jog  = [wall+gap+92, wall+gap+37, board_top+2.5];

  // Lid-side anchor points (underside of panel components).
  a_oled = [lid_pos[0] + oled_c[0] + 12, lid_pos[1] + oled_c[1], lid_pos[2] - 2];
  a_sw1  = [lid_pos[0] + btn_xy[0][0], lid_pos[1] + btn_xy[0][1], lid_pos[2] - 2];
  a_sw2  = [lid_pos[0] + btn_xy[1][0], lid_pos[1] + btn_xy[1][1], lid_pos[2] - 2];
  a_jog  = [lid_pos[0] + jog_c[0], lid_pos[1] + jog_c[1], lid_pos[2] - 2];

  // Long service loops: enough slack to fully remove the top for maintenance.
  wire_path([p_oled, [p_oled[0], p_oled[1]+14, p_oled[2]+slack], [lid_pos[0]-6, lid_pos[1]+16, lid_pos[2]+12], a_oled], 1.2, [0.92, 0.18, 0.18]);
  wire_path([p_sw1,  [p_sw1[0],  p_sw1[1]+12,  p_sw1[2]+slack-2], [lid_pos[0]-8, lid_pos[1]+20, lid_pos[2]+10], a_sw1], 1.0, [0.95, 0.55, 0.1]);
  wire_path([p_sw2,  [p_sw2[0],  p_sw2[1]+10,  p_sw2[2]+slack-3], [lid_pos[0]-9, lid_pos[1]+24, lid_pos[2]+9],  a_sw2], 1.0, [0.2, 0.85, 0.25]);
  wire_path([p_jog,  [p_jog[0],  p_jog[1]+9,   p_jog[2]+slack-4], [lid_pos[0]-10, lid_pos[1]+28, lid_pos[2]+8], a_jog], 1.1, [0.2, 0.65, 0.95]);
}

module board_preview() {
  if (show_board_preview)
    translate([wall+gap, wall+gap, board_z]) {
      color([0.02, 0.42, 0.16]) cube([board_l, board_w, board_t]);

      // Rough module envelopes for visual fit checks (populated board view).
      color([0.08, 0.08, 0.08]) translate([6, 8, board_t]) cube([26, 52, 16]);      // ESP32 devkit
      color([0.15, 0.15, 0.15]) translate([35, 8, board_t]) cube([20, 30, 14]);     // buck module
      color([0.15, 0.15, 0.15]) translate([58, 8, board_t]) cube([20, 30, 14]);     // motor driver
      color([0.65, 0.45, 0.1])  translate([74, 41, board_t]) cylinder(d=16, h=8);    // T1 toroid area

      // Header clusters along the UI edge.
      color([0.95, 0.85, 0.2]) translate([84, 34, board_t]) cube([11, 30, 4]);       // J_OLED/SW/J_TUNE zone

      // Rear connector/header strip area.
      color([0.95, 0.85, 0.2]) translate([8, 0, board_t]) cube([84, 6, 5]);

      // A few visible passives to break up the plain PCB look.
      for (x = [18, 24, 30, 36, 42, 48])
        color([0.88, 0.88, 0.88]) translate([x, 24, board_t]) cube([3, 1.5, 1.1]);
      for (x = [58, 64, 70])
        color([0.92, 0.78, 0.2]) translate([x, 54, board_t]) cube([3.2, 1.8, 1.2]);

      // Additional connector/module accents for richer render.
      color([0.1, 0.1, 0.1]) translate([82, 35, board_t+4]) cube([3, 27, 7]);
      color([0.92, 0.92, 0.92]) translate([9, 1.5, board_t+5]) cube([80, 1.2, 0.8]);
      color([0.2, 0.2, 0.2]) translate([12, 40, board_t]) cylinder(d=5.5, h=10);
      color([0.2, 0.2, 0.2]) translate([50, 46, board_t]) cylinder(d=5.5, h=10);
    }
}

module assembled(lid_lift=0) {
  lid_pos = [0, 0, rim_z + lid_lift];
  color([0.28, 0.46, 0.72]) base();
  panel_connectors_preview();
  coax_pigtails_preview();
  board_preview();
  color([0.28, 0.46, 0.72]) translate(lid_pos) lid();
  lid_panel_parts(lid_pos);
  if (lid_lift > 0) service_wiring(lid_pos, 18);
}

module assembled_clear() {
  lid_pos = [0, 0, rim_z];
  color([0.28, 0.46, 0.72]) base();
  panel_connectors_preview();
  coax_pigtails_preview();
  board_preview();
  // translucent lid for visual inspection of internals
  color([0.35, 0.62, 0.88, 0.35]) translate(lid_pos) lid();
  lid_panel_parts(lid_pos);
}

module service_open() {
  // Lid is fully removed to the side but stays electrically connected.
  lid_pos = [outer_l + 18, 4, rim_z + 4];
  color([0.28, 0.46, 0.72]) base();
  panel_connectors_preview();
  board_preview();
  color([0.28, 0.46, 0.72]) translate(lid_pos) lid();
  lid_panel_parts(lid_pos);
  service_wiring(lid_pos, 28);
}

rotate(view_rot)
if (part == "base") base();
else if (part == "lid") translate([0, outer_w+10, 0]) lid();
else if (part == "assembled") assembled();
else if (part == "assembled_clear") assembled_clear();
else if (part == "lid_off") assembled(20);
else if (part == "service_open") service_open();
else { base(); translate([0, outer_w+10, 0]) lid(); }
