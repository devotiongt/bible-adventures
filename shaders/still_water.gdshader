// Still water of the trough and the well: lighter by the walls (with a light rim that breathes),
// darker at the bottom, and soft glints that move slowly across the surface.
shader_type spatial;
render_mode blend_mix, cull_back, depth_draw_opaque, specular_schlick_ggx;

uniform vec3 deep_color : source_color = vec3(0.22, 0.42, 0.52);
uniform vec3 shallow_color : source_color = vec3(0.48, 0.72, 0.76);
uniform vec3 rim_color : source_color = vec3(0.88, 0.95, 0.95);
uniform float depth_fade = 0.25;     // Meters until the bottom color (a trough is shallow).
uniform float rim_width = 0.035;
uniform sampler2D depth_tex : hint_depth_texture, filter_linear_mipmap;

varying vec3 world_pos;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
			mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float raw = texture(depth_tex, SCREEN_UV).r;
	vec4 view = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, raw, 1.0);
	view.xyz /= view.w;
	float water_depth = max(VERTEX.z - view.z, 0.0);
	vec3 color = mix(shallow_color, deep_color, smoothstep(0.0, depth_fade, water_depth));

	// Light rim by the wall, which slowly widens and narrows.
	float wobble = 0.75 + 0.25 * sin(TIME * 1.3 + (world_pos.x + world_pos.z) * 6.0);
	float rim = 1.0 - smoothstep(rim_width * wobble * 0.6, rim_width * wobble, water_depth);

	// Glints: light wave-shaped patches that drift over time.
	vec2 p = world_pos.xz * 9.0;
	float n = noise(p + vec2(TIME * 0.35, TIME * 0.2)) * 0.6 + noise(p * 2.1 - vec2(TIME * 0.25, 0.0)) * 0.4;
	float glint = smoothstep(0.68, 0.71, n) * (1.0 - smoothstep(0.72, 0.75, n));   // Thin lines, not patches.
	color = mix(color, rim_color, glint * 0.4);

	float nx = noise(p * 0.4 + vec2(TIME * 0.3, 0.0)) - 0.5;
	float nz = noise(p * 0.4 + vec2(0.0, TIME * 0.28)) - 0.5;
	NORMAL = normalize(NORMAL + (VIEW_MATRIX * vec4(nx, 0.0, nz, 0.0)).xyz * 0.3);

	ALBEDO = mix(color, rim_color, rim);
	ALPHA = mix(0.88, 1.0, rim);
	ROUGHNESS = mix(0.08, 0.5, rim);
	SPECULAR = 0.6;
}
