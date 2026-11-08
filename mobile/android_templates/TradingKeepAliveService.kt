package com.example.ai_trade

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import java.net.HttpURLConnection
import java.net.URL

class TradingKeepAliveService : Service() {
    @Volatile private var running = false
    private var worker: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val channelId = "ai_trade_background"

    override fun onCreate() {
        super.onCreate()
        createChannel()
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AITrade:BackgroundMonitor")
        wakeLock?.setReferenceCounted(false)
        try { wakeLock?.acquire() } catch (_: Exception) {}
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification("Background monitor starting")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1001, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(1001, notification)
        }
        if (!running) startBackendMonitor()
        return START_STICKY
    }

    private fun startBackendMonitor() {
        running = true
        worker = Thread {
            while (running) {
                val online = checkBackend()
                val message = if (online) {
                    "Background active • Local trading API connected"
                } else {
                    "Background active • Termux API offline; start api/main.py in Termux"
                }
                (getSystemService(NOTIFICATION_SERVICE) as NotificationManager)
                    .notify(1001, buildNotification(message))
                try { Thread.sleep(15000) } catch (_: InterruptedException) { break }
            }
        }.apply { name = "AITrade-Backend-Watch"; isDaemon = true; start() }
    }

    private fun checkBackend(): Boolean {
        var connection: HttpURLConnection? = null
        return try {
            connection = URL("http://127.0.0.1:8000/health").openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 2500
            connection.readTimeout = 2500
            connection.responseCode in 200..299
        } catch (_: Exception) {
            false
        } finally {
            connection?.disconnect()
        }
    }

    private fun buildNotification(message: String): Notification {
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val pending = launch?.let {
            PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0))
        }
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, channelId)
            else Notification.Builder(this)
        builder.setSmallIcon(android.R.drawable.ic_popup_sync)
            .setContentTitle("AI-Trader")
            .setContentText(message)
            .setStyle(Notification.BigTextStyle().bigText(message))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
        if (pending != null) builder.setContentIntent(pending)
        return builder.build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(NotificationChannel(
                channelId, "AI-Trader background service", NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Keeps AI-Trader monitoring status visible in background" })
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Keep the foreground service running after the app task is swiped away.
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        running = false
        worker?.interrupt()
        try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (_: Exception) {}
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
