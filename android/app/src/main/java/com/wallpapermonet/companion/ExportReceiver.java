package com.wallpapermonet.companion;

import android.app.WallpaperManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.os.Environment;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

/** Only the ADB shell/system can invoke this receiver (protected by DUMP). */
public final class ExportReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (!"com.wallpapermonet.companion.EXPORT".equals(intent.getAction())) return;
        PendingResult pending = goAsync();
        Context app = context.getApplicationContext();
        new Thread(() -> {
            try { export(app); } finally { pending.finish(); }
        }).start();
    }
    private static void export(Context context) {
        File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "WallpaperMonet");
        File status = new File(dir, "status.txt");
        File tmp = new File(dir, "wallpaper.tmp");
        File output = new File(dir, "wallpaper.png");
        String result;
        try {
            if (!Environment.isExternalStorageManager()) throw new Exception("请先打开伴侣应用并授予管理所有文件权限");
            if (!dir.isDirectory() && !dir.mkdirs()) throw new Exception("无法创建导出目录");
            if (status.exists() && !status.delete()) throw new Exception("无法清除旧状态");
            WallpaperManager manager = WallpaperManager.getInstance(context);
            if (manager.getWallpaperInfo() != null) throw new Exception("动态壁纸不支持导出");
            Drawable drawable = manager.getDrawable();
            if (drawable == null) throw new Exception("系统未提供壁纸图像");
            int width = drawable.getIntrinsicWidth(), height = drawable.getIntrinsicHeight();
            if (width <= 0 || height <= 0 || (long) width * height > 100_000_000L) throw new Exception("壁纸尺寸无效或过大");
            Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            try {
                Canvas canvas = new Canvas(bitmap);
                drawable.setBounds(0, 0, width, height); drawable.draw(canvas);
                try (FileOutputStream stream = new FileOutputStream(tmp)) {
                    if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) throw new Exception("PNG 编码失败");
                }
            } finally { bitmap.recycle(); }
            if (output.exists() && !output.delete()) throw new Exception("无法替换旧壁纸文件");
            if (!tmp.renameTo(output)) throw new Exception("无法保存壁纸文件");
            result = "OK";
        } catch (Exception | OutOfMemoryError e) {
            tmp.delete();
            result = "ERROR: " + e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage());
        }
        try {
            if (!dir.exists()) dir.mkdirs();
            try (FileOutputStream stream = new FileOutputStream(status)) {
                stream.write(result.getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception ignored) { /* Desktop reports missing status. */ }
    }
}
