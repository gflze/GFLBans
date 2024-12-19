const PERMISSION = Object.freeze({
    LOGIN: 1 << 0, // Login to the website
    COMMENT: 1 << 1,
    VIEW_IP_ADDR: 1 << 2,
    CREATE_INFRACTION: 1 << 3,
    EDIT_ALL_INFRACTIONS: 1 << 5,
    ATTACH_FILE: 1 << 6,
    WEB_MODERATOR: 1 << 7, // Can edit or delete comments/files on infractions
    MANAGE_SERVERS: 1 << 8,
    MANAGE_VPNS: 1 << 9,
    MANAGE_GROUPS_AND_ADMINS: 1 << 12,
    MANAGE_API_KEYS: 1 << 13,
    BLOCK_ITEMS: 1 << 14, // Add item blocks to infractions
    BLOCK_VOICE: 1 << 15,  // Add voice blocks to infractions
    BLOCK_CHAT: 1 << 16,  // Add chat blocks to infractions
    BAN: 1 << 17,  // Add bans to infractions
    ADMIN_CHAT_BLOCK: 1 << 18,  // Block admin chat
    CALL_ADMIN_BLOCK: 1 << 19,  // Block call admin usage
    SCOPE_GLOBAL: 1 << 21,  // Admins can use GLOBAL infractions
    VPN_CHECK_SKIP: 1 << 22,  // Users with this permission are immune to VPN kicks
    MANAGE_POLICY: 1 << 23,  // Manage tiering policies
    IMMUNE: 1 << 24,  // Immune from infractions
    SKIP_IMMUNITY: 1 << 25,  // Overrides immunity
    RPC_KICK: 1 << 26,
    ASSIGN_TO_SERVER: 1 << 27,  // Assign an infraction to a specific server
    MANAGE_MAP_ICONS: 1 << 28  // Upload and delete map icons
});

const INFRACTION = Object.freeze({
    SYSTEM: 1 << 0, // Created by SYSTEM
    GLOBAL: 1 << 1, // The ban applies to all servers except those ignoring globals
    PERMANENT: 1 << 3, // The ban does not expire
    VPN: 1 << 4, // The IP associated with the ban is likely a VPN (Doesn't show up in check by ip)
    WEB: 1 << 5, // The infraction was created via the web panel (thus has no server associated with it)
    REMOVED: 1 << 6, // The ban was removed by an admin. It still appears, but is not active
    VOICE_BLOCK: 1 << 7, // The player may not speak in game
    CHAT_BLOCK: 1 << 8, // The player may not type in game
    BAN: 1 << 9, // The player may not join the server
    ADMIN_CHAT_BLOCK: 1 << 10, // The player may not use admin chat
    CALL_ADMIN_BAN: 1 << 11, // The player may not call an admin (using !calladmin)
    SESSION: 1 << 12,
    DEC_ONLINE_ONLY: 1 << 13, // Only reduces infraction time when player is online. Invalid for bans and web
    ITEM_BLOCK: 1 << 14, // The player may not use map spawned items
    AUTO_TIER: 1 << 16 // This infraction is considered for tiering purposes.
});

const searchParams = [
    'created',
    'created_comparison_mode',
    'expires',
    'expires_comparison_mode',
    'time_left',
    'time_left_comparison_mode',
    'duration',
    'duration_comparison_mode',

    'gs_service',
    'gs_id',
    'gs_name',
    'ip',
    'admin_id',
    'server',
    'reason',
    'ureason',

    'search',
    'admin',
    'is_expired',
    'is_active',

    'is_system',
    'is_global',
    'is_permanent',
    'is_vpn',
    'is_web',
    'is_removed',
    'is_voice',
    'is_text',
    'is_ban',
    'is_admin_chat',
    'is_call_admin',
    'is_item',
    'is_session',
    'is_decl_online_only'
];

/* eslint-disable-next-line max-len */
const defaultError = 'An error occurred while loading this page. Try again in a few minutes or contact the host if the problem persists.';
const defaultAPIError = 'Received not OK response from the API.';

//Request helper function

async function gbRequest(method='GET', url='', data={}, send_token=false) {
    let q = {
        method: method,
        mode: 'cors',
        cache: 'no-cache',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json'
        },
        redirect: 'follow'
    };

    if (data != null && (method !== 'GET' && method !== 'HEAD')) {
        q.body = JSON.stringify(data);
    }

    if (send_token) {
        q['headers']['X-CSRF-TOKEN'] = getMeta('csrf_token');
    }

    return await fetch(url, q);
}

$(document).ready(function () {
    //Toggle the burger for mobile mode
    $('.navbar-burger').click(function () {
        $('.navbar-burger').toggleClass('is-active');
        $('.navbar-menu').toggleClass('is-active');
    });

    //Switch between light and dark mode
    $('#dark-mode-toggle').click(function () {

        gbRequest('GET', '/toggle_theme').then(resp => {
            if (resp.ok) {
                location.reload();
            } else {
                const errorData = resp.json();
                throw new Error(errorData.detail || defaultAPIError);
            }
        }).catch(function (e) {
            logException(e);
        });
    });

    $('.modal-close').click(function () {
        closeModals();
    });

    $('.modal-background').click(function () {
        if (this.hasAttribute('no-click')) {
            return;
        }
        closeModals();
    });
});

function closeModals() {
    $('.modal').removeClass('is-active');
    $('#htmlRoot').removeClass('is-clipped');
}

//Utility function to get a meta attribute
function getMeta(metaName) {
    const metas = document.getElementsByTagName('meta');

    for (let i = 0; i < metas.length; i++) {
        if (metas[i].getAttribute('name') === metaName) {
            return metas[i].getAttribute('content');
        }
    }

    return '';
}

function showError(error_message=defaultError) {
    closeModals();

    //Setup and show the error modal
    $('#errorMessage').text(error_message);
    $('#errorModal').addClass('is-active');

    $('#htmlRoot').addClass('is-clipped');
}

function getProfileUrl(ply) {
    switch (ply['gs_service']) {
    case 'steam': return '//steamcommunity.com/profiles/' + ply['gs_id'];
    default: return null;
    }
}

function openLinkInNewTab(url) {
    window.open(url, '_blank');
}

//Cache admin data to speed up loading and reduce load on the server
let admin_cache = new Map();

async function get_admin(admin_id) {
    if (admin_cache.has(admin_id)) {
        return admin_cache.get(admin_id);
    }

    let resp = await gbRequest('GET', '/api/gs/admininfo?ips_id=' + admin_id, null);

    if (!resp.ok) {
        throw 'Received Not-OK from API';
    }

    let data = await resp.json();

    admin_cache.set(admin_id, data);

    return data;
}

function insertParam(key, value) {
    let url = new URL(document.URL);

    let sp = url.searchParams;

    sp.set(key, value);

    document.location.search = sp.toString();
}

async function uploadAttachment(infraction, filename, fi, notPublic=false) {
    let hdrs = {'Content-Type': 'application/octet-stream', 'X-CSRF-TOKEN': getMeta('csrf_token')};

    if (notPublic) {
        hdrs['X-Set-Private'] = 'true';
    }

    let resp = await fetch('/api/infractions/' + infraction + '/attachment/' + filename, {
        method: 'POST',
        headers: hdrs,
        body: fi,
        mode: 'cors',
        cache: 'no-cache',
        credentials: 'same-origin',
        redirect: 'follow'
    });

    if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.detail || defaultAPIError);
    }

    return resp;
}

document.addEventListener('load', function () {
    $('.set-default-on-error').on('error', function () {
        this.setAttribute('src', '/static/images/fallback_av.png');
        this.classList.remove('set-default-on-error');
    });
});

function logException(e) {
    console.log(e);
    showError(e);
}
