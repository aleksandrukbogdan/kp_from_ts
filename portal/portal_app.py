from flask import Flask, render_template_string, send_from_directory, request, redirect, url_for, session, make_response
import os
import secrets
from functools import wraps
from users import USERS, validate_user

app = Flask(__name__, static_folder='static')
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Route for serving fonts
@app.route('/static/fonts/<path:filename>')
def serve_font(filename):
    fonts_dir = os.path.join(os.path.dirname(__file__), '..', 'fonts')
    return send_from_directory(fonts_dir, filename)

# Route for serving favicon
@app.route('/static/favicon.svg')
def serve_favicon():
    root_dir = os.path.join(os.path.dirname(__file__), '..')
    return send_from_directory(root_dir, 'favicon.svg')

IS_DEV = os.getenv('IS_DEV', 'false').lower() == 'true'
SERVER_ADDRESS = 'localhost' if IS_DEV else '10.109.50.250'

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>НИР-центр | AI Platform</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        /* ========== Font Face - Onest ========== */
        @font-face {
            font-family: 'Onest';
            src: url('/static/fonts/Onest-Regular.ttf') format('truetype');
            font-weight: 400;
            font-style: normal;
        }
        @font-face {
            font-family: 'Onest';
            src: url('/static/fonts/Onest-Medium.ttf') format('truetype');
            font-weight: 500;
            font-style: normal;
        }
        @font-face {
            font-family: 'Onest';
            src: url('/static/fonts/Onest-Medium.ttf') format('truetype');
            font-weight: 600;
            font-style: normal;
        }
        @font-face {
            font-family: 'Onest';
            src: url('/static/fonts/Onest-Medium.ttf') format('truetype');
            font-weight: 700;
            font-style: normal;
        }
        /* ========== CSS Reset & Variables ========== */
        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        :root {
            /* Material 3 Color Tokens - НИР-центр Brand */
            --md-sys-color-primary: #FF6B35;
            --md-sys-color-on-primary: #FFFFFF;
            --md-sys-color-primary-container: #FFDBCF;
            --md-sys-color-on-primary-container: #2D0F00;
            
            --md-sys-color-secondary: #1E3A5F;
            --md-sys-color-on-secondary: #FFFFFF;
            --md-sys-color-secondary-container: #D1E4FF;
            
            --md-sys-color-surface: #FFFFFF;
            --md-sys-color-surface-variant: #F5F5F5;
            --md-sys-color-on-surface: #1C1B1F;
            --md-sys-color-on-surface-variant: #49454F;
            
            --md-sys-color-background: #FDF8F6;
            --md-sys-color-outline: #E0E0E0;
            --md-sys-color-outline-variant: #CAC4D0;
            
            /* Status Colors */
            --md-sys-color-success: #4CAF50;
            --md-sys-color-warning: #FF9800;
            --md-sys-color-error: #F44336;
            
            /* Elevation */
            --md-sys-elevation-1: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.14);
            --md-sys-elevation-2: 0 3px 6px rgba(0,0,0,0.15), 0 2px 4px rgba(0,0,0,0.12);
            --md-sys-elevation-3: 0 6px 12px rgba(0,0,0,0.15), 0 4px 8px rgba(0,0,0,0.12);
            
            /* Typography */
            --md-sys-typescale-headline-large: 600 2rem/2.5rem 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            --md-sys-typescale-headline-medium: 600 1.75rem/2.25rem 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            --md-sys-typescale-title-large: 600 1.375rem/1.75rem 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            --md-sys-typescale-title-medium: 500 1rem/1.5rem 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            --md-sys-typescale-body-large: 400 1rem/1.5rem 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            --md-sys-typescale-body-medium: 400 0.875rem/1.25rem 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            --md-sys-typescale-label-large: 500 0.875rem/1.25rem 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            
            /* Shape */
            --md-sys-shape-corner-small: 8px;
            --md-sys-shape-corner-medium: 12px;
            --md-sys-shape-corner-large: 16px;
            --md-sys-shape-corner-extra-large: 24px;
        }

        body {
            font-family: 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--md-sys-color-background);
            color: var(--md-sys-color-on-surface);
            min-height: 100vh;
            line-height: 1.5;
            display: flex;
            flex-direction: column;
        }

        /* ========== Header / Navigation ========== */
        .navbar {
            background: var(--md-sys-color-surface);
            box-shadow: var(--md-sys-elevation-1);
            padding: 12px 24px;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .navbar-content {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }

        .brand-logo {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--md-sys-color-primary), #FF8C5F);
            border-radius: var(--md-sys-shape-corner-medium);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 700;
            font-size: 1.25rem;
        }

        .brand-name {
            font: var(--md-sys-typescale-title-large);
            color: var(--md-sys-color-secondary);
            letter-spacing: -0.02em;
        }

        .brand-name span {
            color: var(--md-sys-color-primary);
        }

        .nav-actions {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .icon-btn {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            border: none;
            background: transparent;
            color: var(--md-sys-color-on-surface-variant);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s, color 0.2s;
        }

        .icon-btn:hover {
            background: var(--md-sys-color-surface-variant);
            color: var(--md-sys-color-primary);
        }

        /* ========== Hero Section ========== */
        .hero {
            background: linear-gradient(135deg, var(--md-sys-color-primary) 0%, #FF8C5F 100%);
            padding: 48px 24px;
            margin-bottom: 32px;
        }

        .hero-content {
            max-width: 1400px;
            margin: 0 auto;
            color: var(--md-sys-color-on-primary);
        }

        .hero h1 {
            font: var(--md-sys-typescale-headline-large);
            margin-bottom: 8px;
        }

        .hero p {
            font: var(--md-sys-typescale-body-large);
            opacity: 0.9;
        }

        /* ========== Main Container ========== */
        .main-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 24px 48px;
        }

        /* ========== Section ========== */
        .section {
            margin-bottom: 32px;
        }

        .section-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
        }

        .section-icon {
            width: 40px;
            height: 40px;
            background: var(--md-sys-color-primary-container);
            border-radius: var(--md-sys-shape-corner-medium);
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--md-sys-color-primary);
        }

        .section-title {
            font: var(--md-sys-typescale-title-large);
            color: var(--md-sys-color-secondary);
        }

        /* ========== App Cards Grid ========== */
        .apps-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px;
        }

        .app-card {
            background: var(--md-sys-color-surface);
            border-radius: var(--md-sys-shape-corner-extra-large);
            box-shadow: var(--md-sys-elevation-1);
            padding: 24px;
            transition: box-shadow 0.3s, transform 0.2s;
            display: flex;
            flex-direction: column;
            gap: 16px;
            position: relative;
            overflow: hidden;
        }

        .app-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--md-sys-color-primary), #FF8C5F);
        }

        .app-card:hover {
            box-shadow: var(--md-sys-elevation-3);
            transform: translateY(-4px);
        }

        .app-card-header {
            display: flex;
            align-items: flex-start;
            gap: 16px;
        }

        .app-icon {
            width: 56px;
            height: 56px;
            border-radius: var(--md-sys-shape-corner-large);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.75rem;
            flex-shrink: 0;
        }

        .app-icon.orange {
            background: linear-gradient(135deg, #FF6B35, #FF8C5F);
            color: white;
        }

        .app-icon.blue {
            background: linear-gradient(135deg, #1E3A5F, #3D5A80);
            color: white;
        }

        .app-icon.green {
            background: linear-gradient(135deg, #4CAF50, #66BB6A);
            color: white;
        }

        .app-info {
            flex: 1;
        }

        .app-title {
            font: var(--md-sys-typescale-title-medium);
            color: var(--md-sys-color-on-surface);
            margin-bottom: 4px;
        }

        .app-description {
            font: var(--md-sys-typescale-body-medium);
            color: var(--md-sys-color-on-surface-variant);
        }

        .app-badge {
            font-size: 0.75rem;
            padding: 4px 10px;
            border-radius: 100px;
            background: var(--md-sys-color-primary-container);
            color: var(--md-sys-color-on-primary-container);
            font-weight: 500;
        }

        .app-actions {
            display: flex;
            justify-content: flex-end;
            margin-top: auto;
        }

        .btn-filled {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: var(--md-sys-color-primary);
            color: var(--md-sys-color-on-primary);
            border: none;
            border-radius: 100px;
            font: var(--md-sys-typescale-label-large);
            text-decoration: none;
            cursor: pointer;
            transition: background 0.2s, box-shadow 0.2s;
        }

        .btn-filled:hover {
            background: #E55A28;
            box-shadow: var(--md-sys-elevation-2);
        }

        .btn-filled .material-icons-outlined {
            font-size: 18px;
        }

        /* ========== AI Agent Manager ========== */
        .agent-manager {
            background: var(--md-sys-color-surface);
            border-radius: var(--md-sys-shape-corner-extra-large);
            box-shadow: var(--md-sys-elevation-1);
            padding: 24px;
        }

        .agent-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: var(--md-sys-color-surface-variant);
            border-radius: var(--md-sys-shape-corner-large);
            padding: 20px;
            text-align: center;
        }

        .stat-value {
            font: var(--md-sys-typescale-headline-medium);
            color: var(--md-sys-color-primary);
            margin-bottom: 4px;
        }

        .stat-label {
            font: var(--md-sys-typescale-body-medium);
            color: var(--md-sys-color-on-surface-variant);
        }

        .agent-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .agent-item {
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 16px;
            background: var(--md-sys-color-surface-variant);
            border-radius: var(--md-sys-shape-corner-medium);
        }

        .agent-status {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }

        .agent-status.active {
            background: var(--md-sys-color-success);
            box-shadow: 0 0 8px rgba(76, 175, 80, 0.5);
        }

        .agent-status.idle {
            background: var(--md-sys-color-warning);
        }

        .agent-status.offline {
            background: var(--md-sys-color-outline);
        }

        .agent-name {
            font: var(--md-sys-typescale-title-medium);
            flex: 1;
        }

        .agent-meta {
            font: var(--md-sys-typescale-body-medium);
            color: var(--md-sys-color-on-surface-variant);
        }

        /* ========== Footer ========== */
        .footer {
            background: var(--md-sys-color-secondary);
            color: var(--md-sys-color-on-secondary);
            padding: 24px;
            text-align: center;
        }

        .main-container {
            flex: 1;
        }

        .footer-text {
            font: var(--md-sys-typescale-body-medium);
            opacity: 0.8;
        }

        /* ========== Responsive ========== */
        @media (max-width: 768px) {
            .hero {
                padding: 32px 16px;
            }

            .hero h1 {
                font-size: 1.5rem;
            }

            .main-container {
                padding: 0 16px 32px;
            }

            .apps-grid {
                grid-template-columns: 1fr;
            }

            .agent-stats {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar">
        <div class="navbar-content">
            <a href="/" class="brand">
                <svg class="brand-logo-svg" width="180" height="24" viewBox="0 0 609 79" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M319.017 53.2139H345.819V0H359.178V53.2139H366.82V78.3311H353.446V64.958H305.714V0H319.017V53.2139ZM13.3096 26.9736H40.125V0H53.4941V64.958H40.125V38.8096H13.1826L13.3096 64.958H0V0H13.3096V26.9736ZM81.8975 41.9287L111.534 0H122.273V64.958H108.964V23.3955L79.3271 64.958H68.5879V0H81.8975V41.9287ZM162.524 0C166.44 2.8971e-05 169.99 0.42794 173.172 1.28418C176.354 2.0793 179.046 3.39469 181.249 5.22949C183.513 7.00323 185.227 9.35814 186.39 12.2939C187.613 15.1687 188.194 18.7171 188.133 22.9375C188.072 26.6071 187.43 29.8793 186.206 32.7539C184.982 35.5675 183.268 37.9529 181.065 39.9102C178.924 41.8062 176.323 43.2747 173.264 44.3145C170.265 45.293 166.991 45.7822 163.442 45.7822H150.867V64.958H137.558V0H162.524ZM420.888 11.8359H387.77V26.9736H416.668V38.8096H387.77V53.2139H420.888V64.958H374.468V0H420.888V11.8359ZM446.997 26.9736H473.812V0H487.183V64.958H473.812V38.8096H446.871L446.997 64.958H433.688V0H446.997V26.9736ZM548.319 11.8359H529.214V64.958H515.841V11.8359H496.735V0H548.319V11.8359ZM582.825 0C586.739 1.85201e-05 590.287 0.427941 593.467 1.28418C596.647 2.0793 599.338 3.39462 601.54 5.22949C603.803 7.00321 605.516 9.35819 606.678 12.2939C607.901 15.1687 608.481 18.7171 608.42 22.9375C608.359 26.6071 607.717 29.8793 606.494 32.7539C605.271 35.5674 603.558 37.9529 601.356 39.9102C599.216 41.8062 596.617 43.2747 593.559 44.3145C590.562 45.2931 587.289 45.7822 583.742 45.7822H571.174V64.958H557.872V0H582.825ZM278.936 19.1104C285.266 19.1105 290.398 24.2426 290.398 30.5732C290.398 36.9041 285.266 42.036 278.936 42.0361C273.944 42.0359 269.699 38.8447 268.126 34.3916H224.787C223.214 38.8449 218.969 42.0361 213.978 42.0361C207.647 42.0357 202.515 36.9039 202.515 30.5732C202.515 24.2428 207.647 19.1108 213.978 19.1104C218.967 19.1104 223.21 22.2997 224.785 26.75H268.128C269.702 22.2996 273.946 19.1106 278.936 19.1104ZM571.174 34.0391H583.009C584.66 34.039 586.22 33.8246 587.688 33.3965C589.155 32.9683 590.439 32.2953 591.54 31.3779C592.641 30.4605 593.527 29.3289 594.2 27.9834C594.873 26.6378 595.241 25.0469 595.302 23.2119C595.424 19.053 594.323 16.1168 591.999 14.4043C589.675 12.6918 586.647 11.836 582.917 11.8359H571.174V34.0391ZM150.867 34.0381H162.708C164.36 34.0381 165.92 33.8245 167.389 33.3965C168.857 32.9683 170.143 32.2954 171.244 31.3779C172.346 30.4605 173.233 29.329 173.906 27.9834C174.579 26.6378 174.947 25.0469 175.008 23.2119C175.13 19.053 174.028 16.1169 171.703 14.4043C169.378 12.6918 166.349 11.836 162.616 11.8359H150.867V34.0381Z" fill="#453C69"/>
                </svg>
            </a>
            <div class="nav-actions">
                <span style="font-size: 14px; color: var(--md-sys-color-on-surface-variant);">{{ current_user }}</span>
                <a href="/logout" class="icon-btn" title="Выйти">
                    <span class="material-icons-outlined">logout</span>
                </a>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <section class="hero">
        <div class="hero-content">
            <h1>AI Platform</h1>
            <p>Интеллектуальные решения для автоматизации бизнес-процессов</p>
        </div>
    </section>

    <!-- Main Content -->
    <main class="main-container">
        <!-- Applications Section -->
        <section class="section">
            <div class="section-header">
                <div class="section-icon">
                    <span class="material-icons-outlined">apps</span>
                </div>
                <h2 class="section-title">Приложения</h2>
            </div>
            
            <div class="apps-grid">
                <!-- Агент КП Card -->
                <article class="app-card">
                    <div class="app-card-header">
                        <div class="app-icon orange">
                            <span class="material-icons-outlined">description</span>
                        </div>
                        <div class="app-info">
                            <h3 class="app-title">Агент КП</h3>
                            <p class="app-description">Генерация коммерческих предложений по техническому заданию с использованием AI</p>
                        </div>
                    </div>
                    <div class="app-actions">
                        <a href="http://{{ server_address }}:8501" class="btn-filled">
                            Открыть
                            <span class="material-icons-outlined">arrow_forward</span>
                        </a>
                    </div>
                </article>

                <!-- RAG Card -->
                <article class="app-card">
                    <div class="app-card-header">
                        <div class="app-icon blue">
                            <span class="material-icons-outlined">chat</span>
                        </div>
                        <div class="app-info">
                            <h3 class="app-title">RAG</h3>
                            <p class="app-description">Создайте своего бота!</p>
                        </div>
                    </div>
                    <div class="app-actions">
                        <a href="http://10.109.50.250:5111" class="btn-filled">
                            Открыть
                            <span class="material-icons-outlined">arrow_forward</span>
                        </a>
                    </div>
                </article>
                <article class="app-card">
                    <div class="app-card-header">
                        <div class="app-icon blue">
                            <span class="material-icons-outlined">search</span>
                        </div>
                        <div class="app-info">
                            <h3 class="app-title">ВКС</h3>
                            <p class="app-description">Расшифруйте свою конференцию и получите резюме!</p>
                        </div>
                    </div>
                    <div class="app-actions">
                        <a href="http://10.109.50.250:5000" class="btn-filled">
                            Открыть
                            <span class="material-icons-outlined">arrow_forward</span>
                        </a>
                    </div>
                </article>
                <!-- Placeholder for future apps -->
                <article class="app-card" style="opacity: 0.6; pointer-events: none;">
                    <div class="app-card-header">
                        <div class="app-icon green">
                            <span class="material-icons-outlined">analytics</span>
                        </div>
                        <div class="app-info">
                            <h3 class="app-title">Аннонимайзер</h3>
                            <p class="app-description">Скройте важные данные из своего документа</p>
                        </div>
                        <span class="app-badge">Скоро</span>
                    </div>
                    <div class="app-actions">
                        <a href="#" class="btn-filled">
                            Открыть
                            <span class="material-icons-outlined">arrow_forward</span>
                        </a>
                    </div>
                </article>
            </div>
        </section>

    </main>

    <!-- Footer -->
    <footer class="footer">
        <p class="footer-text">© 2026 НИР-центр. Все права защищены.</p>
    </footer>
</body>
</html>
"""

# Шаблон страницы логина
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход | НИР-центр AI Platform</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        @font-face {
            font-family: 'Onest';
            src: url('/static/fonts/Onest-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'Onest';
            src: url('/static/fonts/Onest-Medium.ttf') format('truetype');
            font-weight: 500;
        }
        
        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        :root {
            --md-sys-color-primary: #FF6B35;
            --md-sys-color-on-primary: #FFFFFF;
            --md-sys-color-primary-container: #FFDBCF;
            --md-sys-color-secondary: #1E3A5F;
            --md-sys-color-surface: #FFFFFF;
            --md-sys-color-surface-variant: #F5F5F5;
            --md-sys-color-background: #FDF8F6;
            --md-sys-color-on-surface: #1C1B1F;
            --md-sys-color-on-surface-variant: #49454F;
            --md-sys-color-outline: #E0E0E0;
            --md-sys-color-error: #F44336;
        }
        
        body {
            font-family: 'Onest', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, var(--md-sys-color-primary) 0%, #FF8C5F 50%, var(--md-sys-color-background) 50%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }
        
        .login-container {
            background: var(--md-sys-color-surface);
            border-radius: 24px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            padding: 48px;
            width: 100%;
            max-width: 420px;
        }
        
        .login-header {
            text-align: center;
            margin-bottom: 32px;
        }
        
        .login-logo {
            width: 64px;
            height: 64px;
            background: linear-gradient(135deg, var(--md-sys-color-primary), #FF8C5F);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 16px;
            color: white;
            font-size: 28px;
            font-weight: 700;
        }
        
        .login-title {
            font-size: 24px;
            font-weight: 600;
            color: var(--md-sys-color-secondary);
            margin-bottom: 8px;
        }
        
        .login-subtitle {
            font-size: 14px;
            color: var(--md-sys-color-on-surface-variant);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            font-size: 14px;
            font-weight: 500;
            color: var(--md-sys-color-on-surface);
            margin-bottom: 8px;
        }
        
        .form-input {
            width: 100%;
            padding: 14px 16px;
            font-size: 15px;
            font-family: 'Onest', sans-serif;
            border: 2px solid var(--md-sys-color-outline);
            border-radius: 12px;
            background: var(--md-sys-color-surface);
            color: var(--md-sys-color-on-surface);
            transition: all 0.2s ease;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--md-sys-color-primary);
            box-shadow: 0 0 0 4px rgba(255, 107, 53, 0.1);
        }
        
        .form-input::placeholder {
            color: var(--md-sys-color-on-surface-variant);
        }
        
        .btn-login {
            width: 100%;
            padding: 14px 24px;
            font-size: 15px;
            font-weight: 500;
            font-family: 'Onest', sans-serif;
            color: var(--md-sys-color-on-primary);
            background: var(--md-sys-color-primary);
            border: none;
            border-radius: 100px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .btn-login:hover {
            background: #E55A28;
            box-shadow: 0 4px 16px rgba(255, 107, 53, 0.4);
            transform: translateY(-2px);
        }
        
        .btn-login:active {
            transform: translateY(0);
        }
        
        .error-message {
            background: #FFEBEE;
            color: var(--md-sys-color-error);
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 14px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .footer-text {
            text-align: center;
            margin-top: 24px;
            font-size: 12px;
            color: var(--md-sys-color-on-surface-variant);
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <div class="login-logo">
                <span class="material-icons-outlined">smart_toy</span>
            </div>
            <h1 class="login-title">Вход в AI Platform</h1>
            <p class="login-subtitle">Введите учётные данные для доступа</p>
        </div>
        
        {% if error %}
        <div class="error-message">
            <span class="material-icons-outlined">error_outline</span>
            {{ error }}
        </div>
        {% endif %}
        
        <form method="POST" action="/login">
            <div class="form-group">
                <label class="form-label" for="username">Логин</label>
                <input type="text" id="username" name="username" class="form-input" placeholder="Введите логин" required autofocus>
            </div>
            <div class="form-group">
                <label class="form-label" for="password">Пароль</label>
                <input type="password" id="password" name="password" class="form-input" placeholder="Введите пароль" required>
            </div>
            <button type="submit" class="btn-login">
                Войти
                <span class="material-icons-outlined">login</span>
            </button>
        </form>
        
        <p class="footer-text">© 2026 НИР-центр. Все права защищены.</p>
    </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if validate_user(username, password):
            session['user'] = username
            # Создаем токен для Streamlit
            auth_token = secrets.token_urlsafe(32)
            session['auth_token'] = auth_token
            response = make_response(redirect(url_for('home')))
            # Устанавливаем cookie для Streamlit
            response.set_cookie('portal_auth_token', auth_token, httponly=False, samesite='Lax', max_age=86400)
            response.set_cookie('portal_user', username, httponly=False, samesite='Lax', max_age=86400)
            return response
        else:
            error = "Неверный логин или пароль"
    
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    response = make_response(redirect(url_for('login')))
    response.delete_cookie('portal_auth_token')
    response.delete_cookie('portal_user')
    return response

@app.route('/api/check-auth')
def check_auth():
    """API endpoint для проверки авторизации из Streamlit"""
    token = request.cookies.get('portal_auth_token') or request.args.get('token')
    user = request.cookies.get('portal_user') or request.args.get('user')
    
    if 'user' in session and session.get('auth_token') == token:
        return {'authenticated': True, 'user': session['user']}
    
    # Также проверяем по cookies напрямую для кросс-контейнерных запросов
    if token and user and user in USERS:
        return {'authenticated': True, 'user': user}
    
    return {'authenticated': False}, 401

@app.route('/')
@login_required
def home():
    return render_template_string(HTML_TEMPLATE, server_address=SERVER_ADDRESS, current_user=session.get('user'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)