let c_server = 0;
let c_row = null;

let server_root = document.getElementById('server_root');

function addServer(server_hostname, ip, map, mod, os, player_text='0/0', id, is_locked=false, full_name) {
    if (c_server % 4 === 0) {
        c_row = document.createElement('div')
        c_row.classList.add('m-1', 'tile', 'is-ancestor', 'server-card', 'mb-5')
        server_root.appendChild(c_row);
    }

    let parent_tile = document.createElement('div');
    parent_tile.classList.add('tile', 'is-3', 'is-parent', 'server-card');

    let child_tile = document.createElement('div');
    child_tile.classList.add('tile', 'is-child', 'box', 'server-card')

    if (map !== '') {
        child_tile.classList.add('tile-hoverable');
        child_tile.setAttribute('data-server-id', id);
    }

    child_tile.classList.add('is-accent');

    parent_tile.appendChild(child_tile);

    //Server hostname and IP address
    let title_root = document.createElement('div')

    let server_name = document.createElement('h1');

    server_name.innerText = server_hostname;
    server_name.classList.add('is-size-5', 'has-text-centered', 'has-text-white', 'nowrap')

    let ip_address = document.createElement('h6')
    ip_address.classList.add('is-size-7', 'has-text-centered', 'has-text-white', 'mb-2')
    ip_address.innerText = ip;

    title_root.appendChild(server_name);
    title_root.appendChild(ip_address);

    //Map image and name
    let map_root = document.createElement('div');

    let map_image = document.createElement('figure');
    map_image.classList.add('image', 'gt-image')

    let map_url;

    if (map === '' || mod === '') {
        map_url = '/static/images/server.webp'
    } else {
        map_url = '/api/maps/' + mod + '/' + map;
    }

    let map_subimage = document.createElement('img');
    map_subimage.setAttribute('src', map_url);
    map_subimage.classList.add('gt-image-inner');
    map_image.appendChild(map_subimage);

    let map_name = document.createElement('h6');
    map_name.classList.add('is-size-7', 'has-text-centered', 'has-text-white', 'mb-3', 'wrappable');

    if (map === '') {
        map_name.innerText = 'Unknown Map'
    } else {
        map_name.innerText = map;
    }

    map_root.appendChild(map_image);
    map_root.appendChild(map_name);

    //Info Icons

    let footer_root = document.createElement('div');

    let info_icon_container = document.createElement('h6');
    info_icon_container.classList.add('has-text-centered', 'has-text-white', 'server-icons');

    //The mod

    let mod_icon_container = document.createElement('span');
    mod_icon_container.classList.add('icon-text', 'server-icon-child');
    let mod_icon_sc = document.createElement('span');
    mod_icon_sc.classList.add('icon', 'img-mod-icon-sc')
    let mod_icon = document.createElement('img');
    mod_icon.setAttribute('src', '/static/images/mods/' + mod + '.webp');
    mod_icon.classList.add('img-mod-icon');

    mod_icon_container.appendChild(mod_icon_sc);
    mod_icon_sc.appendChild(mod_icon);

    info_icon_container.appendChild(mod_icon_container);

    //The operating system

    if (os === 'linux' || os === 'windows' || os === 'apple' || os === 'freebsd') {
        let os_icon_container = document.createElement('span');
        os_icon_container.classList.add('icon-text', 'server-icon-child');
        let os_icon_sc = document.createElement('span');
        os_icon_sc.classList.add('icon')
        let os_icon = document.createElement('i');
        os_icon.classList.add('fab', 'fa-' + os, 'fa-lg');

        os_icon_container.appendChild(os_icon_sc);
        os_icon_sc.appendChild(os_icon);

        info_icon_container.appendChild(os_icon_container);
    }

    if (is_locked) {
        let lock_icon_c = document.createElement('span');
        lock_icon_c.classList.add('icon-text', 'server-icon-child');
        let lock_icon_sc = document.createElement('span');
        lock_icon_sc.classList.add('icon')
        let lock_icon = document.createElement('i');
        lock_icon.classList.add('fas', 'fa-lock', 'fa-lg');

        lock_icon_c.appendChild(lock_icon_sc);
        lock_icon_sc.appendChild(lock_icon);

        info_icon_container.appendChild(lock_icon_c);
    }

    let player_count = document.createElement('h4');
    player_count.classList.add('is-size-5', 'has-text-centered', 'has-text-white')
    player_count.innerText = player_text;

    //footer_root.appendChild(info_icon_container);
    footer_root.appendChild(player_count);

    child_tile.appendChild(title_root);
    child_tile.appendChild(map_root);
    child_tile.appendChild(info_icon_container);
    child_tile.appendChild(footer_root);


    $(map_subimage).on('error', function (ev) {
        ev.target.setAttribute('src', '/static/images/server.webp');
    });

    $(mod_icon).on('error', function (ev) {
        ev.target.remove();

        let ic = 'fa-question'

        if (mod === '') {
            return
        }

        let unknown_icon = document.createElement('i');
        unknown_icon.classList.add('fas', ic, 'fa-lg');
        mod_icon_sc.appendChild(unknown_icon);
    });

    c_row.appendChild(parent_tile);

    if (map !== '') {
        $(child_tile).click(function () {
            serverDetails(id, mod, map, full_name, ip)
        });
    }


    c_server++;
}

// Get the player info
function serverDetails(server_id, mod, map, hostname, ip) {
    let start = (new Date()).getTime();

    setLoading();

    gbRequest('GET', '/api/server/' + server_id + '/players').then(resp => {
        if (resp.ok) {
            resp.json().then(data => {

                unsetLoading();

                let dur = 200 - ((new Date().getTime() - start))

                if (dur > 0) {
                    setTimeout(() => {
                        showServerModal(mod, map, hostname, ip, data, server_id);
                    }, dur)
                } else {
                    showServerModal(mod, map, hostname, ip, data, server_id);
                }
            });
        } else if (resp.status === 503) {
            showError('The server is offline.');
        } else {
            showError('Failed to load player list');
        }
    }).catch(reason => {
        console.log(reason);
        showError('Failed to load player list. Try refreshing the page or the host if the problem persists.')
    });
}

function showServerModal(mod, map, hostname, ip, players, id) {
    closeModals();

    $('#server_modal').addClass('is-active');

    $('#htmlRoot').addClass('is-clipped');

    $('#server_map').attr('src', '/api/maps/' + mod + '/' + map);
    console.log(hostname);
    console.log(ip);
    $('#server_hostname').text(hostname);
    $('#server_ip').text(ip);

    let server_players = document.querySelector("#server_players");

    $(server_players).empty();

    //Do we have RPC_KICK permissions?
    let can_rpc_kick = parseInt(getMeta('active_permissions')) & PERMISSION.RPC_KICK;

    if (players.length === 0) {
        let row = document.createElement('tr');

        let td1 = document.createElement('td');
        td1.innerText = 'No players are connected to this server.';

        row.appendChild(td1);
        server_players.appendChild(row);

        return;
    }

    players.sort(function(a, b) {
        return a.gs_name.toLowerCase() > b.gs_name.toLowerCase();
    });

    for (let i = 0; i < players.length; i++) {
        let row = document.createElement('tr');

        //Create the user photo
        let avatar_row = document.createElement('td');

        if (can_rpc_kick) {
            avatar_row.classList.add('table-player-ditem');
        } else {
            avatar_row.classList.add('table-player-ditem2');
        }

        let avatar_wrapper = document.createElement('div');
        avatar_wrapper.classList.add('is-inline');
        let avatar_image = document.createElement('img');

        if (players[i].hasOwnProperty('gs_avatar')) {
            avatar_image.setAttribute('src', '/file/uploads/' + players[i]['gs_avatar']['file_id'] + '/avatar.webp');
        } else {
            avatar_image.setAttribute('src', '/static/images/fallback_av.png');
        }

        avatar_image.classList.add('user-avatar-table', 'user-avatar', 'set-default-on-error');

        avatar_wrapper.appendChild(avatar_image);
        avatar_row.appendChild(avatar_wrapper);

        let player_name = document.createElement('span');
        player_name.innerText = players[i]['gs_name'];

        avatar_wrapper.appendChild(player_name);

        row.appendChild(avatar_row);

        //Create the buttons
        let button_row = document.createElement('td');

        let profile_btn = document.createElement('button');
        profile_btn.setAttribute('data-tooltip', 'Profile');
        profile_btn.classList.add('button', 'is-outlined', 'is-small', 'ml-1');

        if (can_rpc_kick) {
            button_row.classList.add('w-100px')

            let rpc_kick_btn = document.createElement('button');
            rpc_kick_btn.setAttribute('data-tooltip', 'Kick');
            rpc_kick_btn.classList.add('button', 'is-outlined', 'is-small');

            rpc_kick_btn.classList.add('is-accent')

            if (i === 0) {
                rpc_kick_btn.classList.add('has-tooltip-bottom')
            }

            let kick_icon = document.createElement('i');
            kick_icon.classList.add('fas', 'fa-user-slash');

            rpc_kick_btn.appendChild(kick_icon);

            rpc_kick_btn.onclick = function () {
                rpc_kick_btn.classList.add('is-loading')
                gbRequest('POST', '/api/rpc/kick', {
                    'server_id': id,
                    'player': {
                        'gs_service': players[i]['gs_service'],
                        'gs_id': players[i]['gs_id']
                    }
                }).then(function (resp) {
                    rpc_kick_btn.classList.remove('is-loading');
                    if (resp.ok) {
                        //Refresh the modal
                        serverDetails(id, mod, map, hostname, ip);
                    } else if (resp.status === 504) {
                        showError('The server did not respond in time. The player may still be kicked.');
                    } else {
                        throw 'Received Non-OK response from the API'
                    }
                }).catch(function (r) {
                    console.log(r);
                    rpc_kick_btn.classList.remove('is-loading');
                    showError('Failed to kick player. Check console for more information!')
                })
            }

            button_row.appendChild(rpc_kick_btn);
        } else {
            button_row.classList.add('w-50px')
        }

        if (i === 0) {
            profile_btn.classList.add('has-tooltip-bottom')
        }

        profile_btn.classList.add('is-accent')

        let profile_icon = document.createElement('i');
        profile_icon.classList.add('fas', 'fa-address-card');

        let profile_url = getProfileUrl(players[i]);

        if (profile_url == null) {
            profile_btn.setAttribute('disabled', '1')
        } else {
            profile_btn.onclick = function () {
                openLinkInNewTab(profile_url);
            }
        }

        profile_btn.appendChild(profile_icon);

        button_row.appendChild(profile_btn);

        row.appendChild(button_row);
        server_players.appendChild(row);
    }
}

function setupEmptySNotice() {
    let server_root = document.getElementById('server_root');

    server_root.classList.add('has-text-centered')

    let icon = document.createElement('i');
    icon.classList.add('fas', 'fa-question', 'mt-5', 'nf-icon', 'text-primary');

    let text = document.createElement('h1');
    text.innerText = 'No Servers';
    text.classList.add('is-size-1');

    let subtext = document.createElement('p');
    subtext.innerText = 'You can add servers in the Admin control panel.'
    subtext.classList.add('mb-5');

    server_root.appendChild(icon);
    server_root.appendChild(text);
    server_root.appendChild(subtext);
}

$(document).ready(function () {

    let start = (new Date()).getTime();

    setLoading();

    gbRequest('GET', '/api/server/?enabled_only=true').then(resp => {
        function _loadS() {
                unsetLoading();
                if (resp.ok) {
                resp.json().then(j => {
                        if (j.length <= 0) {
                            //Show a little message stating that there are no servers
                            setupEmptySNotice();
                            return;
                        }

                        for (let i = 0; i < j.length; i++) {
                            let item = j[i];

                            let name = 'Unnamed Server';

                            if (item.hasOwnProperty('friendly_name')) {
                                name = item['friendly_name'];
                            }

                            let full_name = name;

                            if (item.hasOwnProperty('hostname')) {
                                full_name = item['hostname'];
                            }

                            if (!item['online']) {
                                addServer(name, `${item['ip']}:${item['game_port']}`, '', '', '', 'Offline', item['id'],false, full_name);
                            } else {
                                addServer(name, `${item['ip']}:${item['game_port']}`, item['map'], item['mod'], item['os'], `${item['player_count']} / ${item['max_players']}`, item['id'], item['is_locked'], full_name);
                            }
                        }
                    }
                );

            } else {
                throw 'Non-OK response from the server'
            }
        }

        let dur = 500 - ((new Date()).getTime() - start);

        if (dur > 0) {
            setTimeout(_loadS, dur)
        } else {
            _loadS();
        }
    }).catch(err => {
        console.log(err);
        showError();
    });
});