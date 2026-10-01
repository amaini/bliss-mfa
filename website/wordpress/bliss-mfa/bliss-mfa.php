<?php
/**
 * Plugin Name: Bliss MFA Client Portal
 * Description: Adds a Bliss MFA product introduction and secure client portal link with [bliss_mfa].
 * Version: 0.1.0
 * Requires PHP: 8.1
 */
if (!defined('ABSPATH')) { exit; }

add_action('admin_init', function () {
    register_setting('bliss_mfa', 'bliss_mfa_portal_url', array(
        'type' => 'string',
        'default' => 'https://license.blissitek.ca/customer',
        'sanitize_callback' => function ($value) {
            $url = esc_url_raw(trim($value), array('https'));
            $host = wp_parse_url($url, PHP_URL_HOST);
            if (!$host || wp_parse_url($url, PHP_URL_SCHEME) !== 'https' ||
                wp_parse_url($url, PHP_URL_USER) || wp_parse_url($url, PHP_URL_PASS)) {
                add_settings_error('bliss_mfa_portal_url', 'invalid_url', 'Enter an HTTPS client portal URL.');
                return get_option('bliss_mfa_portal_url', 'https://license.blissitek.ca/customer');
            }
            return $url;
        },
    ));
});

add_action('admin_menu', function () {
    add_options_page('Bliss MFA', 'Bliss MFA', 'manage_options', 'bliss-mfa', function () {
        if (!current_user_can('manage_options')) { return; }
        echo '<div class="wrap"><h1>Bliss MFA client portal</h1><p>Add <code>[bliss_mfa]</code> to your application page, then add that page to your navigation menu.</p>';
        echo '<form method="post" action="options.php">';
        settings_fields('bliss_mfa');
        echo '<label for="bliss-mfa-url">Client portal URL</label> <input class="regular-text" id="bliss-mfa-url" name="bliss_mfa_portal_url" type="url" value="' . esc_attr(get_option('bliss_mfa_portal_url', 'https://license.blissitek.ca/customer')) . '" required>';
        submit_button();
        echo '</form></div>';
    });
});

add_shortcode('bliss_mfa', function () {
    $url = get_option('bliss_mfa_portal_url', 'https://license.blissitek.ca/customer');
    return '<section class="bliss-mfa-product"><h2>Bliss Secure MFA for Windows and RDP</h2>' .
        '<p>Protect your team’s Windows access with authenticator codes. Manage users and their authenticator keys inside your own environment.</p>' .
        '<ol><li>Choose and purchase your protected-user seats.</li><li>Install your local appliance and activate your license.</li><li>Enroll your team and verify protected RDP access.</li></ol>' .
        '<p><a class="button wp-element-button" href="' . esc_url($url) . '">Purchase seats or manage your account</a></p></section>';
});
