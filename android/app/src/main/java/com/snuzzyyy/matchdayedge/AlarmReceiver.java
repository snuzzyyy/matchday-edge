package com.snuzzyyy.matchdayedge;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/** Timed bet alerts (5 minutes before kick-off, kick-off) that the site schedules; they fire even when the app is closed. */
public class AlarmReceiver extends BroadcastReceiver {
    private static PendingIntent pending(Context c, String key, String title, String body) {
        Intent i = new Intent(c, AlarmReceiver.class);
        i.setAction("com.snuzzyyy.matchdayedge.ALERT." + key);
        i.putExtra("key", key);
        i.putExtra("title", title);
        i.putExtra("body", body);
        return PendingIntent.getBroadcast(c, key.hashCode(), i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    static void schedule(Context c, String key, long at, String title, String body) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null || key == null) return;
        PendingIntent p = pending(c, key, title, body);
        try {
            if (Build.VERSION.SDK_INT >= 31 && !am.canScheduleExactAlarms()) am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, p);
            else am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, p);
        } catch (Exception e) {
            try { am.set(AlarmManager.RTC_WAKEUP, at, p); } catch (Exception ignored) { }
        }
    }

    static void cancel(Context c, String key) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null || key == null) return;
        try { am.cancel(pending(c, key, "", "")); } catch (Exception ignored) { }
    }

    @Override
    public void onReceive(Context c, Intent i) {
        MainActivity.postAlert(c, i.getStringExtra("title"), i.getStringExtra("body"), i.getStringExtra("key"));
    }
}
