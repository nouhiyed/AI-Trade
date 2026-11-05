import 'package:flutter/material.dart';

void main() => runApp(const AITradeApp());

class AITradeApp extends StatefulWidget {
  const AITradeApp({super.key});

  @override
  State<AITradeApp> createState() => _AITradeAppState();
}

class _AITradeAppState extends State<AITradeApp> {
  bool arabic = true;
  bool liveMode = false;
  int page = 0;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF080D18),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00D6A0),
          surface: Color(0xFF111B2B),
        ),
      ),
      home: Directionality(
        textDirection:
            arabic ? TextDirection.rtl : TextDirection.ltr,
        child: Scaffold(
          appBar: AppBar(
            backgroundColor: const Color(0xFF080D18),
            title: const Text(
              'AI TRADE',
              style: TextStyle(
                fontWeight: FontWeight.w900,
                letterSpacing: 2,
              ),
            ),
            actions: [
              IconButton(
                onPressed: () => setState(() => arabic = !arabic),
                icon: const Icon(Icons.language),
              ),
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.notifications_none),
              ),
              const SizedBox(width: 8),
            ],
          ),
          body: IndexedStack(
            index: page,
            children: [
              dashboard(),
              agentsPage(),
              walletPage(),
              settingsPage(),
            ],
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: page,
            onDestinationSelected: (v) =>
                setState(() => page = v),
            backgroundColor: const Color(0xFF111B2B),
            indicatorColor: const Color(0xFF164C45),
            destinations: [
              NavigationDestination(
                icon: const Icon(Icons.dashboard_outlined),
                label: arabic ? 'الرئيسية' : 'Home',
              ),
              NavigationDestination(
                icon: const Icon(Icons.smart_toy_outlined),
                label: arabic ? 'الوكلاء' : 'Agents',
              ),
              NavigationDestination(
                icon: const Icon(Icons.account_balance_wallet_outlined),
                label: arabic ? 'المحفظة' : 'Wallet',
              ),
              NavigationDestination(
                icon: const Icon(Icons.settings_outlined),
                label: arabic ? 'الإعدادات' : 'Settings',
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget dashboard() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF173C43), Color(0xFF142137)],
            ),
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: Colors.white12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(arabic ? 'إجمالي الرصيد' : 'TOTAL BALANCE',
                  style: const TextStyle(color: Colors.white70)),
              const SizedBox(height: 10),
              const Text(
                '\$1,000.00',
                style: TextStyle(
                  fontSize: 34,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                arabic
                    ? 'رصيد تجريبي مبدئي - غير متصل بالمنصة'
                    : 'Initial demo balance - not connected',
                style: const TextStyle(
                    color: Color(0xFF00D6A0), fontSize: 12),
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  balanceItem(arabic ? 'الأرباح' : 'PROFIT', '\$0.00'),
                  balanceItem(arabic ? 'المتاح' : 'AVAILABLE', '\$1,000'),
                  balanceItem(arabic ? 'الصفقات' : 'TRADES', '0'),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Text(
          arabic ? 'وضع التداول' : 'TRADING MODE',
          style: const TextStyle(
              fontSize: 17, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: modeButton(
                arabic ? 'تداول تجريبي' : 'DEMO',
                !liveMode,
                () => setState(() => liveMode = false),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: modeButton(
                arabic ? 'تداول حقيقي' : 'LIVE',
                liveMode,
                () => setState(() => liveMode = true),
              ),
            ),
          ],
        ),
        if (liveMode)
          Container(
            margin: const EdgeInsets.only(top: 10),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.red.withOpacity(.12),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.redAccent),
            ),
            child: Text(
              arabic
                  ? 'التداول الحقيقي غير مفعّل. يتطلب ربط Binance واختبارات الأمان وموافقتك.'
                  : 'Live trading is locked until Binance connection and safety approval.',
              style: const TextStyle(color: Colors.redAccent),
            ),
          ),
        const SizedBox(height: 22),
        Text(
          arabic ? 'الوكلاء الذكيون' : 'AI AGENTS',
          style: const TextStyle(
              fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        agentCard('Futures Agent', 'BTC • ETH • SOL',
            arabic ? 'جاهز للمراقبة' : 'Monitoring ready',
            Icons.candlestick_chart),
        agentCard('Spot Agent', 'Binance Spot USDT',
            arabic ? 'جاهز للمراقبة' : 'Monitoring ready',
            Icons.show_chart),
        agentCard('Alpha Agent', 'Binance Alpha',
            arabic ? 'بانتظار مصدر البيانات' : 'Data source pending',
            Icons.auto_awesome),
        const SizedBox(height: 20),
        Text(
          arabic ? 'آخر الصفقات' : 'RECENT TRADES',
          style: const TextStyle(
              fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 10),
        emptyCard(arabic ? 'لا توجد صفقات بعد' : 'No trades yet'),
      ],
    );
  }

  Widget balanceItem(String title, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title,
            style: const TextStyle(
                color: Colors.white60, fontSize: 11)),
        const SizedBox(height: 5),
        Text(value,
            style: const TextStyle(
                fontWeight: FontWeight.bold, fontSize: 15)),
      ],
    );
  }

  Widget modeButton(
      String title, bool selected, VoidCallback action) {
    return ElevatedButton(
      onPressed: action,
      style: ElevatedButton.styleFrom(
        backgroundColor: selected
            ? const Color(0xFF00A982)
            : const Color(0xFF182438),
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(vertical: 16),
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(13)),
      ),
      child: Text(title),
    );
  }

  Widget agentCard(
      String name, String subtitle, String status, IconData icon) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: const Color(0xFF111B2B),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white10),
      ),
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: const Color(0xFF173C43),
            child: Icon(icon, color: const Color(0xFF00D6A0)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: const TextStyle(
                        fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Text(subtitle,
                    style: const TextStyle(
                        color: Colors.white60, fontSize: 12)),
                const SizedBox(height: 5),
                Text(status,
                    style: const TextStyle(
                        color: Color(0xFF00D6A0), fontSize: 11)),
              ],
            ),
          ),
          const Icon(Icons.circle,
              color: Color(0xFF00D6A0), size: 9),
        ],
      ),
    );
  }

  Widget agentsPage() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          arabic ? 'إدارة الوكلاء' : 'AGENT MANAGEMENT',
          style: const TextStyle(
              fontSize: 22, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 18),
        agentCard('Futures Agent', 'USDT Perpetual Contracts',
            arabic ? 'مستقل - قيد التجهيز' : 'Independent - setup pending',
            Icons.candlestick_chart),
        agentCard('Spot Agent', 'Binance Spot Markets',
            arabic ? 'مستقل - قيد التجهيز' : 'Independent - setup pending',
            Icons.show_chart),
        agentCard('Alpha Agent', 'Binance Alpha Tokens',
            arabic ? 'مستقل - قيد التجهيز' : 'Independent - setup pending',
            Icons.auto_awesome),
        const SizedBox(height: 15),
        emptyCard(arabic
            ? 'سيظهر هنا تحليل كل وكيل وإشاراته وسجل تعلمه.'
            : 'Each agent analysis, signals and learning history will appear here.'),
      ],
    );
  }

  Widget walletPage() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          arabic ? 'المحفظة الموحدة' : 'UNIFIED WALLET',
          style: const TextStyle(
              fontSize: 22, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 18),
        emptyCard(arabic
            ? 'رصيد تجريبي: 1,000 USDT'
            : 'Demo balance: 1,000 USDT'),
        const SizedBox(height: 12),
        walletItem('Binance Spot', '\$0.00'),
        walletItem('Binance Futures', '\$0.00'),
        walletItem('Binance Funding', '\$0.00'),
        const SizedBox(height: 15),
        Text(
          arabic
              ? 'الأرصدة الحقيقية ستظهر بعد ربط حساب Binance بشكل آمن.'
              : 'Real balances will appear after secure Binance connection.',
          style: const TextStyle(color: Colors.white60),
        ),
      ],
    );
  }

  Widget walletItem(String name, String amount) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(17),
      decoration: BoxDecoration(
        color: const Color(0xFF111B2B),
        borderRadius: BorderRadius.circular(15),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(name),
          Text(amount,
              style: const TextStyle(
                  fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget settingsPage() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          arabic ? 'الإعدادات' : 'SETTINGS',
          style: const TextStyle(
              fontSize: 22, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 15),
        ListTile(
          leading: const Icon(Icons.language),
          title: Text(arabic ? 'لغة التطبيق' : 'App Language'),
          subtitle: Text(arabic ? 'العربية' : 'English'),
          trailing: const Icon(Icons.swap_horiz),
          onTap: () => setState(() => arabic = !arabic),
        ),
        const Divider(color: Colors.white12),
        ListTile(
          leading: const Icon(Icons.security),
          title: Text(arabic ? 'الأمان والمخاطر' : 'Security & Risk'),
          subtitle: Text(arabic
              ? 'إعدادات الحماية وحدود الخسارة'
              : 'Protection and loss limits'),
        ),
        const Divider(color: Colors.white12),
        ListTile(
          leading: const Icon(Icons.psychology),
          title: Text(arabic ? 'التعلم الذاتي' : 'Self Learning'),
          subtitle: Text(arabic
              ? 'تحليل أداء الوكلاء وتطوير الاستراتيجيات'
              : 'Agent performance and strategy improvement'),
        ),
        const Divider(color: Colors.white12),
        ListTile(
          leading: const Icon(Icons.emergency),
          title: Text(arabic ? 'الإيقاف الطارئ' : 'Emergency Stop'),
          subtitle: Text(arabic
              ? 'سيتم ربطه بمحرك التداول لاحقاً'
              : 'Will be connected to the trading engine later'),
        ),
      ],
    );
  }

  Widget emptyCard(String message) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF111B2B),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: Colors.white10),
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: const TextStyle(color: Colors.white60),
      ),
    );
  }
}

