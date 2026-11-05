// Diorama effect (tilt-shift): blurs the top and bottom of the screen, plus a soft vignette.
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;
uniform float focus_center = 0.5;
uniform float focus_size = 0.8;
uniform float max_blur = 0.0;
uniform float vignette = 0.12;

void fragment() {
	vec2 uv = SCREEN_UV;
	float dist = abs(uv.y - focus_center);
	float blur = smoothstep(focus_size * 0.5, focus_size * 0.5 + 0.35, dist) * max_blur;
	vec2 px = SCREEN_PIXEL_SIZE * (1.0 + blur * 1.5);
	vec3 color = textureLod(screen_tex, uv, blur).rgb * 0.4;
	color += textureLod(screen_tex, uv + vec2(px.x, px.y), blur).rgb * 0.15;
	color += textureLod(screen_tex, uv + vec2(-px.x, px.y), blur).rgb * 0.15;
	color += textureLod(screen_tex, uv + vec2(px.x, -px.y), blur).rgb * 0.15;
	color += textureLod(screen_tex, uv + vec2(-px.x, -px.y), blur).rgb * 0.15;
	vec2 c = uv - 0.5;
	color *= 1.0 - dot(c, c) * vignette * 2.0;
	COLOR = vec4(color, 1.0);
}
