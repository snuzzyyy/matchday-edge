package com.snuzzyyy.matchdayedge;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ClipData;
import android.content.ContentValues;
import android.graphics.BitmapFactory;
import android.provider.MediaStore;
import android.util.Base64;
import android.widget.Toast;
import java.io.OutputStream;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** Full-screen wrapper around the live Accabox site. Content updates come from the site itself. */
public class MainActivity extends Activity {
    private static final String HOME = "https://snuzzyyy.github.io/matchday-edge/";
    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private static final int PICK_FILE = 42;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#080C18"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " MatchdayEdgeApp/1.6");
        // Lets the site open the phone's own share menu (WhatsApp, Messages, Snapchat...)
        web.addJavascriptInterface(new Object() {
            @JavascriptInterface
            public void share(String text) {
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("text/plain");
                send.putExtra(Intent.EXTRA_TEXT, text);
                runOnUiThread(() -> { try { startActivity(Intent.createChooser(send, "Share")); } catch (Exception ignored) { } });
            }
            // Bet alerts: the site calls these to show a phone notification
            @JavascriptInterface
            public boolean canNotify() {
                return Build.VERSION.SDK_INT < 33 || checkSelfPermission("android.permission.POST_NOTIFICATIONS") == PackageManager.PERMISSION_GRANTED;
            }
            @JavascriptInterface
            public void askNotify() {
                if (Build.VERSION.SDK_INT >= 33) runOnUiThread(() -> requestPermissions(new String[] { "android.permission.POST_NOTIFICATIONS" }, 7));
            }
            @JavascriptInterface
            public void notify(String title, String body, String tag) {
                showAlert(title, body, tag);
            }
            // Pictures made by the site (tweet cards): save to the phone's photos, or share with text
            @JavascriptInterface
            public String saveImage(String b64, String name) {
                Uri u = storeImage(b64, name);
                if (u == null) return "error";
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Saved to your photos (Pictures > Accabox)", Toast.LENGTH_SHORT).show());
                return "ok";
            }
            @JavascriptInterface
            public String shareImage(String b64, String name, String text) {
                Uri u = storeImage(b64, name);
                if (u == null) return "error";
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("image/png");
                send.putExtra(Intent.EXTRA_STREAM, u);
                if (text != null && !text.isEmpty()) send.putExtra(Intent.EXTRA_TEXT, text);
                send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                runOnUiThread(() -> { try { startActivity(Intent.createChooser(send, "Share")); } catch (Exception ignored) { } });
                return "ok";
            }
        }, "MDEApp");
        // Downloads (like a new version of the app) go to the phone's browser
        web.setDownloadListener((url, ua, cd, mime, len) -> { try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); } catch (Exception ignored) { } });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                String url = u.toString();
                // Stay inside the app for the site itself and sign-in links; open bookmakers and everything else in the browser.
                if (url.startsWith(HOME) || "snuzzyyy.github.io".equals(u.getHost()) || (u.getHost() != null && u.getHost().endsWith("supabase.co"))) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true;
            }
        });
        // Lets the site's photo upload open the phone's gallery / file picker
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    Intent pick = params.createIntent();
                    pick.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(Intent.createChooser(pick, "Choose a photo"), PICK_FILE);
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });
        setContentView(web);
        if (state != null) web.restoreState(state);
        else web.loadUrl(HOME);
    }

    /** Writes a PNG into Pictures/Accabox and returns its address, or null if it couldn't. */
    private Uri storeImage(String b64, String name) {
        try {
            byte[] bytes = Base64.decode(b64, Base64.DEFAULT);
            String file = (name == null || name.isEmpty()) ? "accabox-" + System.currentTimeMillis() : name.replaceAll("[^A-Za-z0-9._-]", "");
            if (!file.endsWith(".png")) file += ".png";
            if (Build.VERSION.SDK_INT >= 29) {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Images.Media.DISPLAY_NAME, file);
                v.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
                v.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Accabox");
                v.put(MediaStore.Images.Media.IS_PENDING, 1);
                Uri u = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v);
                if (u == null) return null;
                try (OutputStream o = getContentResolver().openOutputStream(u)) { if (o == null) return null; o.write(bytes); }
                ContentValues done = new ContentValues();
                done.put(MediaStore.Images.Media.IS_PENDING, 0);
                getContentResolver().update(u, done, null, null);
                return u;
            }
            // older phones need the storage permission once
            if (checkSelfPermission("android.permission.WRITE_EXTERNAL_STORAGE") != PackageManager.PERMISSION_GRANTED) {
                runOnUiThread(() -> { requestPermissions(new String[] { "android.permission.WRITE_EXTERNAL_STORAGE" }, 8); Toast.makeText(MainActivity.this, "Allow storage, then tap Save again", Toast.LENGTH_LONG).show(); });
                return null;
            }
            String saved = MediaStore.Images.Media.insertImage(getContentResolver(), BitmapFactory.decodeByteArray(bytes, 0, bytes.length), file, "Accabox");
            return saved == null ? null : Uri.parse(saved);
        } catch (Exception e) {
            return null;
        }
    }

    private void showAlert(String title, String body, String tag) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel("bets") == null) {
            NotificationChannel ch = new NotificationChannel("bets", "Bet alerts", NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription("When a leg lands, a player is close, or a bet settles");
            nm.createNotificationChannel(ch);
        }
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        open.putExtra("hash", "#mybets");
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, "bets") : new Notification.Builder(this);
        b.setSmallIcon(R.drawable.ic_notify).setContentTitle(title).setContentText(body)
         .setStyle(new Notification.BigTextStyle().bigText(body)).setAutoCancel(true).setContentIntent(pi).setColor(Color.parseColor("#FF7A2F"));
        try { nm.notify(tag == null ? (int) System.currentTimeMillis() : tag.hashCode(), b.build()); } catch (Exception ignored) { }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        String h = intent.getStringExtra("hash");
        if (h != null && web != null) web.evaluateJavascript("location.hash='" + h.replace("'", "") + "'", null);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == PICK_FILE && fileCallback != null) {
            Uri[] picked = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            // some gallery apps hand the photo back as "clip data" instead
            if (picked == null && resultCode == RESULT_OK && data != null && data.getClipData() != null && data.getClipData().getItemCount() > 0) {
                ClipData c = data.getClipData();
                picked = new Uri[] { c.getItemAt(0).getUri() };
            }
            fileCallback.onReceiveValue(picked);
            fileCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }

    @Override
    protected void onResume() { super.onResume(); web.onResume(); }

    @Override
    protected void onPause() { web.onPause(); super.onPause(); }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
