import 'dart:math' as math;
import 'package:flutter/material.dart';

void main() => runApp(const AITradeApp());

const bg = Color(0xFF070B16);
const panel = Color(0xFF111A2D);
const panel2 = Color(0xFF19253B);
const cyan = Color(0xFF00E5C3);
const blue = Color(0xFF438CFF);
const purple = Color(0xFF9865FF);
const muted = Color(0xFF8794AD);

class AITradeApp extends StatelessWidget {
  const AITradeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AI TRADE',
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: bg,
        colorScheme: const ColorScheme.dark(
          primary: cyan,
          secondary: purple,
          surface: panel,
        ),
        useMaterial3: true,
      ),
      home: const Dashboard(),
    );
  }
}

class Dashboard extends StatefulWidget {
  const Dashboard({super.key});

  @override
  State<Dashboard> createState() => _DashboardState();
}

class _DashboardState extends State<Dashboard>
    with SingleTickerProviderStateMixin {
  late final AnimationController animation;
  int tab = 0;
  bool arabic = true;
  bool demo = true;
  bool emergency = false;
  final List<bool> agentsEnabled = [true, true, true];

  String tr(String ar, String en) => arabic ? ar : en;

  @override
  void initState() {
    super.initState();
    animation = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 12),
    )..repeat();
  }

  @override
  void dispose() {
    animation.dispose();
    super.dispose();
  }

  void notify(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: panel2,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final titles = [
      tr('مركز القيادة', 'Command Center'),
      tr('الوكلاء الذكيون', 'AI Agents'),
      tr('الأسواق', 'Markets'),
      tr('المحفظة', 'Portfolio'),
      tr('الإعدادات', 'Settings'),
    ];

    return Directionality(
      textDirection: arabic ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        body: SafeArea(
          child: Column(
            children: [
              _header(titles[tab]),
              Expanded(
                child: IndexedStack(
                  index: tab,
                  children: [
                    _home(),
                    _agentsPage(),
                    _marketsPage(),
                    _walletPage(),
                    _settingsPage(),
                  ],
                ),
              ),
            ],
          ),
        ),
        bottomNavigationBar: _navigation(),
      ),
    );
  }

  Widget _header(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 12, 18, 10),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              gradient: const LinearGradient(colors: [cyan, purple]),
              boxShadow: [
                BoxShadow(
                  color: cyan.withOpacity(.18),
                  blurRadius: 18,
                ),
              ],
            ),
            child: const Icon(Icons.auto_awesome, color: bg),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'AI TRADE',
                  style: TextStyle(
                    fontSize: 21,
                    letterSpacing: 2.4,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                Text(title, style: const TextStyle(color: muted, fontSize: 11)),
              ],
            ),
          ),
          IconButton(
            onPressed: () => setState(() => arabic = !arabic),
            icon: const Icon(Icons.language, color: cyan),
          ),
          IconButton(
            onPressed: () => notify(tr('لا توجد إشعارات جديدة', 'No new alerts')),
            icon: const Icon(Icons.notifications_none),
          ),
        ],
      ),
    );
  }

  Widget _home() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(17, 8, 17, 24),
      children: [
        _hero(),
        const SizedBox(height: 16),
        _balanceCard(),
        const SizedBox(height: 21),
        _section(tr('تحليل السوق', 'MARKET OVERVIEW'), 'BTC / USDT'),
        const SizedBox(height: 10),
        _marketChart(),
        const SizedBox(height: 21),
        _section(tr('شبكة الوكلاء', 'AI AGENT NETWORK'), '3 AGENTS'),
        const SizedBox(height: 10),
        _networkCard(),
        const SizedBox(height: 20),
        _section(tr('وكلاء التداول', 'TRADING AGENTS'), 'CONTROL'),
        const SizedBox(height: 10),
        _agentTile(0, 'Futures AI', 'BTC • ETH • SOL', Icons.candlestick_chart, cyan),
        _agentTile(1, 'Spot AI', 'BINANCE SPOT', Icons.show_chart, blue),
        _agentTile(2, 'Alpha AI', 'BINANCE ALPHA', Icons.auto_awesome, purple),
        const SizedBox(height: 18),
        _section(tr('آخر النشاطات', 'RECENT ACTIVITY'), 'HISTORY'),
        _empty(
          Icons.receipt_long,
          tr('لا توجد صفقات بعد', 'No trades yet'),
          tr('ستظهر الصفقات هنا بعد بدء التداول التجريبي', 'Trades will appear here after paper trading starts'),
        ),
      ],
    );
  }

  Widget _hero() {
    return Container(
      height: 218,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(25),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF142D43), Color(0xFF17132F), Color(0xFF0B1221)],
        ),
        border: Border.all(color: cyan.withOpacity(.20)),
      ),
      child: Stack(
        children: [
          Positioned.fill(child: CustomPaint(painter: _GridPainter())),
          Positioned(
            right: -8,
            top: 0,
            bottom: 0,
            width: 190,
            child: AnimatedBuilder(
              animation: animation,
              builder: (_, __) => CustomPaint(
                painter: _OrbPainter(animation.value),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.bolt, color: cyan, size: 17),
                    const SizedBox(width: 5),
                    Text(
                      tr('منظومة التداول الذكية', 'INTELLIGENT TRADING CORE'),
                      style: const TextStyle(
                        color: cyan,
                        fontSize: 9,
                        letterSpacing: 1.2,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
                const Spacer(),
                Text(
                  tr('ثلاثة وكلاء.', 'THREE AGENTS.'),
                  style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w900),
                ),
                Text(
                  tr('عقل تداول واحد.', 'ONE TRADING MIND.'),
                  style: const TextStyle(fontSize: 22, color: cyan, fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: 205,
                  child: Text(
                    tr('تحليل مستقل، إدارة مخاطر مشتركة، وقرارات منسقة.', 'Independent analysis, shared risk and coordinated decisions.'),
                    style: const TextStyle(color: Color(0xFFB5C1D6), fontSize: 11, height: 1.5),
                  ),
                ),
                const Spacer(),
                _pill(
                  emergency ? Colors.redAccent : cyan,
                  emergency ? tr('الإيقاف الطارئ مفعل', 'EMERGENCY STOP') : tr('النظام في وضع الاستعداد', 'SYSTEM STANDBY'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _balanceCard() {
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(tr('إجمالي المحفظة', 'TOTAL PORTFOLIO'),
                  style: const TextStyle(color: muted, fontSize: 10, letterSpacing: 1.2)),
              const Spacer(),
              _pill(demo ? blue : cyan, demo ? 'DEMO' : 'LIVE'),
            ],
          ),
          const SizedBox(height: 8),
          const Text('\$1,000.00', style: TextStyle(fontSize: 34, fontWeight: FontWeight.w900)),
          Text(
            tr('رصيد تجريبي • غير متصل بـ Binance', 'Demo balance • Not connected to Binance'),
            style: const TextStyle(color: muted, fontSize: 10),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              _metric(tr('الربح', 'PROFIT'), '\$0.00', cyan),
              _metric(tr('المتاح', 'AVAILABLE'), '\$1,000', Colors.white),
              _metric(tr('الصفقات', 'TRADES'), '0', Colors.white),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(child: _modeButton(tr('تداول تجريبي', 'DEMO MODE'), demo, () => setState(() => demo = true))),
              const SizedBox(width: 9),
              Expanded(child: _modeButton(tr('تداول حقيقي', 'LIVE MODE'), !demo, _liveWarning)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metric(String label, String value, Color color) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: muted, fontSize: 10)),
          const SizedBox(height: 5),
          Text(value, style: TextStyle(color: color, fontSize: 15, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _modeButton(String label, bool active, VoidCallback onTap) {
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: onTap,
      child: Container(
        height: 43,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: active ? cyan.withOpacity(.13) : panel2,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: active ? cyan : Colors.white12),
        ),
        child: Text(label, style: TextStyle(color: active ? cyan : Colors.white70, fontSize: 11, fontWeight: FontWeight.bold)),
      ),
    );
  }

  void _liveWarning() {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: panel,
        title: Text(tr('التداول الحقيقي غير متاح', 'Live trading is locked')),
        content: Text(tr(
          'يجب أولاً ربط Binance API وإكمال اختبارات التداول التجريبي وإعداد حدود المخاطر. لا توجد أوامر حقيقية تُرسل حالياً.',
          'Connect Binance API, complete paper-trading validation and configure risk limits first. No real orders are sent currently.',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK')),
        ],
      ),
    );
  }

  Widget _section(String title, String trailing) {
    return Row(
      children: [
        Expanded(child: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800))),
        Text(trailing, style: const TextStyle(color: cyan, fontSize: 9, fontWeight: FontWeight.bold)),
      ],
    );
  }

  Widget _marketChart() {
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Text('BTC / USDT', style: TextStyle(fontWeight: FontWeight.bold)),
              Spacer(),
              Text('PREVIEW', style: TextStyle(color: muted, fontSize: 9)),
            ],
          ),
          const SizedBox(height: 8),
          const Row(
            children: [
              Text('\$67,420.00', style: TextStyle(fontSize: 23, fontWeight: FontWeight.w900)),
              SizedBox(width: 8),
              Text('+2.41%', style: TextStyle(color: cyan, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 13),
          SizedBox(height: 125, width: double.infinity, child: CustomPaint(painter: _ChartPainter())),
          const SizedBox(height: 12),
          const Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _TinyStat('RSI', '56.8'),
              _TinyStat('MACD', '+124.5'),
              _TinyStat('TREND', 'BULLISH'),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            tr('رسم توضيحي فقط • بيانات السوق غير متصلة بعد', 'Illustrative chart • Market feed not connected'),
            style: const TextStyle(color: muted, fontSize: 9),
          ),
        ],
      ),
    );
  }

  Widget _networkCard() {
    return Container(
      height: 220,
      decoration: BoxDecoration(
        color: panel,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withOpacity(.06)),
      ),
      child: AnimatedBuilder(
        animation: animation,
        builder: (_, __) => CustomPaint(
          painter: _NetworkPainter(animation.value),
          child: Center(
            child: Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(colors: [cyan, blue, purple]),
                boxShadow: [BoxShadow(color: cyan.withOpacity(.35), blurRadius: 25, spreadRadius: 3)],
              ),
              child: const Icon(Icons.memory, color: Colors.white, size: 37),
            ),
          ),
        ),
      ),
    );
  }

  Widget _agentTile(int index, String name, String subtitle, IconData icon, Color color) {
    final active = agentsEnabled[index] && !emergency;
    return InkWell(
      borderRadius: BorderRadius.circular(17),
      onTap: () => _agentDetails(name, subtitle, icon, color),
      child: Container(
        margin: const EdgeInsets.only(bottom: 9),
        padding: const EdgeInsets.all(13),
        decoration: BoxDecoration(
          color: panel,
          borderRadius: BorderRadius.circular(17),
          border: Border.all(color: color.withOpacity(.17)),
        ),
        child: Row(
          children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color.withOpacity(.12),
                boxShadow: [BoxShadow(color: color.withOpacity(.12), blurRadius: 15)],
              ),
              child: Icon(icon, color: color, size: 23),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                  const SizedBox(height: 4),
                  Text(subtitle, style: const TextStyle(color: muted, fontSize: 10)),
                  const SizedBox(height: 5),
                  Text(active ? tr('مفعّل في الواجهة', 'ENABLED IN UI') : tr('متوقف في الواجهة', 'DISABLED IN UI'),
                      style: TextStyle(color: active ? color : Colors.orangeAccent, fontSize: 9)),
                ],
              ),
            ),
            Switch(
              value: active,
              activeColor: cyan,
              onChanged: (v) {
                setState(() => agentsEnabled[index] = v);
              },
            ),
          ],
        ),
      ),
    );
  }

  void _agentDetails(String name, String subtitle, IconData icon, Color color) {
    showModalBottomSheet(
      context: context,
      backgroundColor: panel,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 36),
            const SizedBox(height: 13),
            Text(name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            Text(subtitle, style: const TextStyle(color: muted)),
            const SizedBox(height: 15),
            Text(tr(
              'هذه واجهة تحكم أولية. سيُربط الوكيل بمحرك التحليل والتنفيذ في مرحلة ربط الخادم.',
              'This is an initial control interface. The agent engine will be connected in the backend integration phase.',
            ), style: const TextStyle(height: 1.5)),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }

  Widget _agentsPage() {
    return ListView(
      padding: const EdgeInsets.all(17),
      children: [
        _hero(),
        const SizedBox(height: 20),
        _section(tr('إدارة الوكلاء', 'AGENT MANAGEMENT'), '3 AGENTS'),
        const SizedBox(height: 12),
        _agentTile(0, 'Futures AI', 'USDT PERPETUAL CONTRACTS', Icons.candlestick_chart, cyan),
        _agentTile(1, 'Spot AI', 'BINANCE SPOT PAIRS', Icons.show_chart, blue),
        _agentTile(2, 'Alpha AI', 'BINANCE ALPHA TOKENS', Icons.auto_awesome, purple),
        const SizedBox(height: 20),
        _section(tr('التحكم المركزي', 'CENTRAL CONTROL'), ''),
        const SizedBox(height: 12),
        _controlTile(
          tr('الإيقاف الطارئ', 'Emergency stop'),
          emergency ? tr('مفعل', 'ACTIVE') : tr('غير مفعل', 'INACTIVE'),
          Icons.power_settings_new,
          Colors.redAccent,
          () {
            setState(() => emergency = !emergency);
            notify(tr('تغير وضع الواجهة فقط؛ لم يتم إرسال أمر للخادم', 'UI state changed; no server command was sent'));
          },
        ),
        const SizedBox(height: 10),
        const Text(
          'تنبيه: عناصر التحكم حالياً محلية داخل التطبيق ولا تتحكم بخادم أو حساب تداول.',
          style: TextStyle(color: muted, fontSize: 10),
        ),
      ],
    );
  }

  Widget _marketsPage() {
    return ListView(
      padding: const EdgeInsets.all(17),
      children: [
        _section(tr('مراقبة الأسواق', 'MARKET SCANNER'), 'PREVIEW'),
        const SizedBox(height: 12),
        _marketRow('BTC / USDT', '\$67,420.00', '+2.41%', cyan),
        _marketRow('ETH / USDT', '\$3,520.50', '+1.28%', cyan),
        _marketRow('SOL / USDT', '\$182.30', '-0.74%', Colors.redAccent),
        const SizedBox(height: 20),
        _section(tr('محركات التحليل', 'ANALYSIS ENGINES'), ''),
        const SizedBox(height: 12),
        _infoTile(Icons.show_chart, 'Technical Analysis', 'RSI • MACD • EMA • ADX', cyan),
        _infoTile(Icons.account_tree, 'Market Structure', 'BOS • CHoCH • Liquidity', purple),
        _infoTile(Icons.waterfall_chart, 'Order Book', 'Spread • Imbalance • Depth', blue),
        const SizedBox(height: 12),
        const Text(
          'الأسعار والمؤشرات المعروضة هنا بيانات شكلية للمعاينة وليست أسعاراً حية.',
          style: TextStyle(color: muted, fontSize: 10),
        ),
      ],
    );
  }

  Widget _marketRow(String symbol, String price, String change, Color color) {
    return Container(
      margin: const EdgeInsets.only(bottom: 9),
      padding: const EdgeInsets.all(16),
      decoration: _decoration(),
      child: Row(
        children: [
          const Icon(Icons.currency_bitcoin, color: cyan, size: 25),
          const SizedBox(width: 12),
          Expanded(child: Text(symbol, style: const TextStyle(fontWeight: FontWeight.bold))),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(price, style: const TextStyle(fontWeight: FontWeight.bold)),
              Text(change, style: TextStyle(color: color, fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _walletPage() {
    return ListView(
      padding: const EdgeInsets.all(17),
      children: [
        Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(23),
            gradient: const LinearGradient(colors: [Color(0xFF173C4A), Color(0xFF202044)]),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(tr('إجمالي المحفظة', 'TOTAL PORTFOLIO'), style: const TextStyle(color: muted, fontSize: 11)),
              const SizedBox(height: 12),
              const Text('\$1,000.00', style: TextStyle(fontSize: 34, fontWeight: FontWeight.w900)),
              const SizedBox(height: 8),
              Text(tr('رصيد تجريبي غير متصل', 'Demo balance - not connected'), style: const TextStyle(color: cyan, fontSize: 11)),
            ],
          ),
        ),
        const SizedBox(height: 22),
        _section(tr('محافظ Binance', 'BINANCE WALLETS'), '3 ACCOUNTS'),
        const SizedBox(height: 12),
        _infoTile(Icons.account_balance_wallet, 'Spot Wallet', 'USDT • BTC • ETH', cyan),
        _infoTile(Icons.swap_vert_circle, 'Futures Wallet', 'USDT-M • COIN-M', purple),
        _infoTile(Icons.token, 'Funding Wallet', 'Funding assets', blue),
        const SizedBox(height: 15),
        const Text(
          'ربط الحساب سيُضاف لاحقاً عبر API بصلاحيات التداول فقط ودون صلاحية السحب.',
          style: TextStyle(color: muted, fontSize: 11, height: 1.5),
        ),
      ],
    );
  }

  Widget _settingsPage() {
    return ListView(
      padding: const EdgeInsets.all(17),
      children: [
        _section(tr('إعدادات النظام', 'SYSTEM SETTINGS'), 'AI TRADE'),
        const SizedBox(height: 12),
        _controlTile(
          tr('لغة التطبيق', 'App language'),
          arabic ? 'العربية' : 'English',
          Icons.language,
          cyan,
          () => setState(() => arabic = !arabic),
        ),
        _controlTile(
          tr('وضع التداول', 'Trading mode'),
          demo ? tr('تجريبي', 'DEMO') : 'LIVE',
          Icons.swap_horiz,
          purple,
          () => setState(() => demo = !demo),
        ),
        _controlTile(
          tr('الإيقاف الطارئ', 'Emergency stop'),
          emergency ? tr('مفعل', 'ACTIVE') : tr('غير مفعل', 'INACTIVE'),
          Icons.power_settings_new,
          Colors.redAccent,
          () => setState(() => emergency = !emergency),
        ),
        _controlTile(
          tr('الأمان وإدارة المخاطر', 'Security & risk'),
          tr('الإعدادات', 'CONFIGURE'),
          Icons.shield_outlined,
          cyan,
          () => notify(tr('سيتم ربط إعدادات المخاطر لاحقاً', 'Risk settings will be connected later')),
        ),
        const SizedBox(height: 20),
        _empty(Icons.memory, 'AI TRADE', 'Version 1.0 • Flutter Android'),
      ],
    );
  }

  Widget _controlTile(String title, String value, IconData icon, Color color, VoidCallback action) {
    return InkWell(
      onTap: action,
      borderRadius: BorderRadius.circular(15),
      child: Container(
        margin: const EdgeInsets.only(bottom: 9),
        padding: const EdgeInsets.all(15),
        decoration: _decoration(),
        child: Row(
          children: [
            Icon(icon, color: color, size: 23),
            const SizedBox(width: 12),
            Expanded(child: Text(title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13))),
            Text(value, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.bold)),
            const SizedBox(width: 5),
            const Icon(Icons.chevron_right, color: muted, size: 19),
          ],
        ),
      ),
    );
  }

  Widget _infoTile(IconData icon, String title, String subtitle, Color color) {
    return Container(
      margin: const EdgeInsets.only(bottom: 9),
      padding: const EdgeInsets.all(15),
      decoration: _decoration(),
      child: Row(
        children: [
          Icon(icon, color: color, size: 25),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Text(subtitle, style: const TextStyle(color: muted, fontSize: 10)),
              ],
            ),
          ),
          const Icon(Icons.chevron_right, color: muted),
        ],
      ),
    );
  }

  Widget _empty(IconData icon, String title, String subtitle) {
    return Container(
      padding: const EdgeInsets.all(23),
      decoration: _decoration(),
      child: Column(
        children: [
          Icon(icon, color: muted, size: 34),
          const SizedBox(height: 10),
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Text(subtitle, textAlign: TextAlign.center, style: const TextStyle(color: muted, fontSize: 10)),
        ],
      ),
    );
  }

  Widget _pill(Color color, String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(.35)),
      ),
      child: Text(text, style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.bold)),
    );
  }

  Widget _card({required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: _decoration(),
      child: child,
    );
  }

  BoxDecoration _decoration() => BoxDecoration(
        color: panel,
        borderRadius: BorderRadius.circular(19),
        border: Border.all(color: Colors.white.withOpacity(.06)),
      );

  Widget _navigation() {
    final items = [
      (Icons.dashboard_rounded, tr('الرئيسية', 'Home')),
      (Icons.hub_rounded, tr('الوكلاء', 'Agents')),
      (Icons.candlestick_chart, tr('الأسواق', 'Markets')),
      (Icons.account_balance_wallet, tr('المحفظة', 'Wallet')),
      (Icons.settings_rounded, tr('الإعدادات', 'Settings')),
    ];
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF0C1322),
        border: Border(top: BorderSide(color: Color(0xFF202B40))),
      ),
      child: NavigationBar(
        height: 68,
        backgroundColor: const Color(0xFF0C1322),
        indicatorColor: cyan.withOpacity(.13),
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: items.map((item) => NavigationDestination(
          icon: Icon(item.$1, color: muted, size: 21),
          selectedIcon: Icon(item.$1, color: cyan, size: 22),
          label: item.$2,
        )).toList(),
      ),
    );
  }
}

class _TinyStat extends StatelessWidget {
  final String label;
  final String value;
  const _TinyStat(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: muted, fontSize: 9)),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(color: cyan, fontSize: 11, fontWeight: FontWeight.bold)),
      ],
    );
  }
}

class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..color = cyan.withOpacity(.055)
      ..strokeWidth = .6;
    for (double x = 0; x < size.width; x += 25) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), p);
    }
    for (double y = 0; y < size.height; y += 25) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), p);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _OrbPainter extends CustomPainter {
  final double phase;
  _OrbPainter(this.phase);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = 56.0;
    final glow = Paint()
      ..color = cyan.withOpacity(.08)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 28);
    canvas.drawCircle(center, radius + 14, glow);

    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = cyan.withOpacity(.55);
    for (int i = 0; i < 3; i++) {
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(phase * math.pi * 2 + i * math.pi / 3);
      canvas.drawOval(
        Rect.fromCenter(center: Offset.zero, width: radius * 2, height: radius * .72),
        ring..color = i.isEven ? cyan.withOpacity(.65) : purple.withOpacity(.6),
      );
      canvas.restore();
    }

    final core = Paint()
      ..shader = const RadialGradient(
        colors: [Color(0xFFB9FFF5), cyan, Color(0xFF087C9B), Color(0xFF182A58)],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, 31, core);

    final dot = Paint()..color = Colors.white;
    for (int i = 0; i < 8; i++) {
      final a = phase * math.pi * 2 + i * math.pi / 4;
      final point = center + Offset(math.cos(a) * 70, math.sin(a) * 48);
      canvas.drawCircle(point, 2.5, dot..color = i.isEven ? cyan : purple);
    }
  }

  @override
  bool shouldRepaint(covariant _OrbPainter oldDelegate) => oldDelegate.phase != phase;
}

class _NetworkPainter extends CustomPainter {
  final double phase;
  _NetworkPainter(this.phase);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width * .34, 78.0);
    final points = <Offset>[];
    for (int i = 0; i < 3; i++) {
      final a = phase * math.pi * 2 + i * math.pi * 2 / 3 - math.pi / 2;
      points.add(center + Offset(math.cos(a) * radius, math.sin(a) * radius));
    }
    final line = Paint()
      ..color = cyan.withOpacity(.35)
      ..strokeWidth = 1.2;
    for (final point in points) {
      canvas.drawLine(center, point, line);
    }
    canvas.drawLine(points[0], points[1], line..color = purple.withOpacity(.4));
    canvas.drawLine(points[1], points[2], line..color = blue.withOpacity(.4));
    canvas.drawLine(points[2], points[0], line..color = cyan.withOpacity(.4));

    for (int i = 0; i < points.length; i++) {
      final color = [cyan, purple, blue][i];
      canvas.drawCircle(points[i], 19, Paint()..color = color.withOpacity(.12));
      canvas.drawCircle(points[i], 8, Paint()..color = color);
      canvas.drawCircle(points[i], 3, Paint()..color = Colors.white);
    }

    final orbitPoint = center + Offset(
      math.cos(phase * math.pi * 4) * radius * .72,
      math.sin(phase * math.pi * 4) * radius * .72,
    );
    canvas.drawCircle(orbitPoint, 4, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(covariant _NetworkPainter oldDelegate) => oldDelegate.phase != phase;
}

class _ChartPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = Colors.white.withOpacity(.055)
      ..strokeWidth = .7;
    for (int i = 1; i < 5; i++) {
      final y = size.height * i / 5;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }

    const values = [
      .72, .66, .70, .58, .63, .52, .57, .43, .49, .38,
      .45, .33, .39, .27, .35, .22, .29, .16, .23, .13,
      .19, .10, .15, .07
    ];
    final path = Path();
    for (int i = 0; i < values.length; i++) {
      final point = Offset(
        size.width * i / (values.length - 1),
        size.height * values[i],
      );
      if (i == 0) {
        path.moveTo(point.dx, point.dy);
      } else {
        path.lineTo(point.dx, point.dy);
      }
    }

    final fill = Path.from(path)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();

    canvas.drawPath(
      fill,
      Paint()
        ..shader = LinearGradient(
          colors: [cyan.withOpacity(.23), cyan.withOpacity(0)],
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
        ).createShader(Offset.zero & size),
    );

    canvas.drawPath(
      path,
      Paint()
        ..color = cyan
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );

    final last = Offset(size.width, size.height * values.last);
    canvas.drawCircle(last, 4, Paint()..color = cyan);
    canvas.drawCircle(
      last,
      8,
      Paint()
        ..color = cyan.withOpacity(.2)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5),
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
