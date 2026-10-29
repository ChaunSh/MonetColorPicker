package com.wallpapermonet.companion;

import android.app.Activity;
import android.content.Intent;
import android.content.res.Resources;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.util.Locale;

/** Native, Material 3-inspired presentation of the current Android color resources. */
public final class MainActivity extends Activity {
    private static final int[] TONES = {0, 10, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000};
    private static final String[] PALETTES = {"accent1", "accent2", "accent3", "neutral1", "neutral2"};
    private static final String[] LABELS = {"主强调色", "次强调色", "第三强调色", "中性色", "次中性色"};
    private int background, surface, ink, muted, primary, onPrimary;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
    }

    @Override protected void onResume() {
        super.onResume();
        render(); // Refresh permission and color resources after returning from Settings.
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private int sysColor(String name, int fallback) {
        if (Build.VERSION.SDK_INT < 31) return fallback;
        int id = getResources().getIdentifier("system_" + name, "color", "android");
        try { return id == 0 ? fallback : getColor(id); }
        catch (Resources.NotFoundException e) { return fallback; }
    }
    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); return d;
    }
    private TextView text(String value, int sp, int color, boolean bold) {
        TextView t = new TextView(this); t.setText(value); t.setTextSize(sp); t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        t.setIncludeFontPadding(true); return t;
    }
    private void gap(LinearLayout parent, int height) {
        View v = new View(this); parent.addView(v, new LinearLayout.LayoutParams(1, dp(height)));
    }
    private LinearLayout card(LinearLayout parent) {
        LinearLayout c = new LinearLayout(this); c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(dp(20), dp(20), dp(20), dp(20)); c.setBackground(rounded(surface, 24));
        parent.addView(c, new LinearLayout.LayoutParams(-1, -2)); return c;
    }
    private void render() {
        background = sysColor("neutral1_10", Color.rgb(250, 248, 255));
        surface = sysColor("neutral1_50", Color.rgb(243, 239, 250));
        ink = sysColor("neutral1_900", Color.rgb(35, 31, 43));
        muted = sysColor("neutral2_700", Color.rgb(89, 82, 98));
        primary = sysColor("accent1_600", Color.rgb(103, 80, 164));
        onPrimary = sysColor("accent1_0", Color.WHITE);
        getWindow().setStatusBarColor(background); getWindow().setNavigationBarColor(background);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(background);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(24), dp(20), dp(32)); scroll.addView(root); setContentView(scroll);
        TextView eyebrow = text("WALLPAPER MONET", 12, primary, true); eyebrow.setLetterSpacing(.1f); root.addView(eyebrow);
        gap(root, 8); root.addView(text("壁纸与动态配色", 28, ink, true));
        gap(root, 6); root.addView(text("查看系统色阶，并连接电脑读取壁纸", 14, muted, false));
        gap(root, 24);
        LinearLayout permission = card(root);
        permission.addView(text("壁纸访问", 20, ink, true)); gap(permission, 8);
        permission.addView(text(Environment.isExternalStorageManager() ? "●  所有文件权限已授予" : "●  尚未授予所有文件权限", 14, primary, true));
        gap(permission, 8);
        permission.addView(text("授权后，电脑可通过 ADB 请求导出主屏静态壁纸。文件保存在 Download/WallpaperMonet，使用后可自行删除。", 14, muted, false));
        gap(permission, 16);
        TextView button = text("管理所有文件权限", 14, onPrimary, true); button.setGravity(Gravity.CENTER);
        button.setPadding(dp(20), dp(12), dp(20), dp(12)); button.setBackground(rounded(primary, 100));
        button.setOnClickListener(v -> {
            Intent i = new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:" + getPackageName()));
            try { startActivity(i); } catch (Exception e) { startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)); }
        });
        permission.addView(button, new LinearLayout.LayoutParams(-1, -2));
        gap(root, 16);
        LinearLayout palette = card(root);
        palette.addView(text("当前系统动态配色", 20, ink, true)); gap(palette, 8);
        palette.addView(text("展示系统提供的 Monet 色阶。颜色通常来自壁纸，但也受系统设置和厂商实现影响；点击色块可查看色值。", 14, muted, false));
        gap(palette, 18);
        if (Build.VERSION.SDK_INT < 31 || getResources().getIdentifier("system_accent1_0", "color", "android") == 0) {
            palette.addView(text("当前系统未提供 Android 12 动态色资源。", 14, muted, false));
        } else {
            for (int i = 0; i < PALETTES.length; i++) {
                palette.addView(text(LABELS[i] + "  ·  " + PALETTES[i], 13, ink, true)); gap(palette, 7);
                LinearLayout row = new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
                for (int tone : TONES) {
                    String name = "system_" + PALETTES[i] + "_" + tone;
                    int id = getResources().getIdentifier(name, "color", "android");
                    int color = id == 0 ? Color.TRANSPARENT : getColor(id);
                    View swatch = new View(this); swatch.setBackgroundColor(color);
                    final String detail = name + "  " + String.format(Locale.ROOT, "#%06X", color & 0xffffff);
                    swatch.setContentDescription(detail); swatch.setOnClickListener(v -> Toast.makeText(this, detail, Toast.LENGTH_SHORT).show());
                    row.addView(swatch, new LinearLayout.LayoutParams(0, dp(38), 1));
                }
                palette.addView(row, new LinearLayout.LayoutParams(-1, dp(38))); gap(palette, 15);
            }
            palette.addView(text("浅色 → 深色  ·  13 个色阶", 12, muted, false));
        }
        gap(root, 16); root.addView(text("动态壁纸、锁屏壁纸或厂商保护的壁纸可能无法导出。系统色阶与桌面程序计算的预览可能不同。", 12, muted, false));
    }
}
