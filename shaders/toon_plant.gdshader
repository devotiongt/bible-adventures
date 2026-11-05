// Plants in the reference style (trees, shrubs, flowers): per-vertex color, wind sway
// based on height and some light passing through the leaves.
shader_type spatial;
render_mode cull_disabled;

uniform float wind_strength = 0.04;
uniform float wind_speed = 1.3;
uniform float sway_height = 1.0; // Local height at which the sway is full.
uniform float roughness = 0.9;

void vertex() {
	vec3 world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float h = clamp(VERTEX.y / sway_height, 0.0, 1.0);
	float t = TIME * wind_speed + world.x * 0.12 + world.z * 0.09;
	VERTEX += vec3(sin(t), 0.0, cos(t * 0.83)) * h * h * wind_strength;
}

void fragment() {
	ALBEDO = COLOR.rgb;
	ROUGHNESS = roughness;
	SPECULAR = 0.2;
	BACKLIGHT = vec3(0.25, 0.3, 0.15);
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
}
