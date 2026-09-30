<?php
// Run with mbstring enabled and a NEW disposable state directory argument.
// An optional second argument selects another shipped class implementation.
if ($argc < 2 || !is_dir($argv[1])) {
    throw new RuntimeException('Supply an empty disposable state directory');
}
require_once($argv[2] ?? dirname(__DIR__).'/multiotp.class.php');

class TokenWriteFailureEngine extends Multiotp {
    public $failTokenWrites = false;
    function WriteTokenData($write_token_data_array = []) {
        return $this->failTokenWrites ? FALSE : parent::WriteTokenData($write_token_data_array);
    }
}

function check($condition, $label) {
    if (!$condition) { throw new RuntimeException($label); }
    echo 'PASS '.$label.PHP_EOL;
}

$engine = new TokenWriteFailureEngine('disposable-test-key', false, $argv[1]);
check('' == $engine->GetUsersList(), 'state directory starts empty');
$user = 'token_regression_disposable';
check((bool)$engine->FastCreateUser($user, '', '', 0), 'create software user');
$before = $engine->GetUserTokenSeed();
$engine->SetUserTokenDeltaTime(330);
$engine->SetUserTokenLastLogin(time() + 330);
check($engine->WriteUserData(), 'persist previous token clock');
check($engine->RemoveTokenFromUser($user), 'remove software token reports success');
check($engine->ReadUserData($user), 'read rotated software user');
check($before !== $engine->GetUserTokenSeed(), 'software removal rotates seed');
check(0 == $engine->GetUserTokenDeltaTime() && 0 == $engine->GetUserTokenLastLogin(), 'rotation clears prior token clock');
$before = $engine->GetUserTokenSeed();
check(!$engine->AssignTokenToUser($user, 'missing_serial'), 'missing token rejected');
check(!$engine->CheckTokenExists('missing_serial', false), 'missing assignment creates no token');
check($engine->ReadUserData($user) && $before === $engine->GetUserTokenSeed(), 'missing assignment preserves user seed');
check(!$engine->RemoveTokenFromUser('missing_user'), 'missing user removal rejected');
check(!$engine->ReadUserData('missing_user'), 'missing removal creates no user');

$serial = 'regression_serial';
check($engine->CreateToken($serial, 'totp', bin2hex(random_bytes(20)), 6, 30), 'create imported token');
check(!$engine->AssignTokenToUser('missing_user', $serial), 'missing user assignment rejected');
check(!$engine->ReadUserData('missing_user'), 'missing assignment creates no user');
check($engine->AssignTokenToUser($user, $serial), 'assign existing token');
check($engine->ReadUserData($user), 'read assigned user');
$before = $engine->GetUserTokenSeed();
$engine->failTokenWrites = true;
check(!$engine->RemoveTokenFromUser($user), 'failed attribution write reports failure');
check($engine->ReadUserData($user) && $before === $engine->GetUserTokenSeed(), 'failed attribution write does not rotate user seed');
$engine->failTokenWrites = false;
check($engine->RemoveTokenFromUser($user), 'remove assigned token reports success');
check($engine->ReadUserData($user) && '' === $engine->GetUserTokenSerialNumber(), 'assigned token detached');
check($engine->ReadTokenData($serial) && '' === $engine->GetTokenAttributedUsers(), 'token attribution persisted');
check($engine->DeleteUser($user), 'delete disposable user');
check($engine->DeleteToken($serial), 'delete disposable token');
check('' === $engine->GetUsersList() && '' === $engine->GetTokensList(), 'state cleaned');
