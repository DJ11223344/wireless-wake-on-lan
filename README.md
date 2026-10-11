# wwol — Wake-on-LAN from a Raspberry Pi

wwol is a tiny web app for a Raspberry Pi. Open it in any browser on your home
network, see which PCs are on, and press **Wake Up** to turn one on with a
Wake-on-LAN "magic packet". It uses only Python's standard library — no pip, no
Node — so it runs comfortably on a Pi Zero.

Built for:
- **Raspberry Pi Zero** running **DietPi**, networked with a USB-Ethernet adapter
- **Raspberry Pi 3B** running **Raspberry Pi OS Lite**

> **Security:** wwol has no login. Anyone on your network can wake your PCs.
> Keep it on your home network and never port-forward it to the internet. To
> use it away from home, connect to your home network through a VPN.

## Why I built it

Some of my PCs connect to my home network over Wi-Fi, and sometimes I need to
reach them remotely. That's a problem when they're switched off, and
Wake-on-LAN almost never works over Wi-Fi.

Each of those PCs still has an Ethernet port that isn't being used. wwol puts
it to work: a Raspberry Pi, which uses very little power, is cabled into that
spare port, so I can turn the PC on remotely and then connect to it. Because I
can wake the PCs only when I need them, I don't have to leave them running
24/7, which saves money on the power bill.

When I'm away from home, I reach the page through my VPN. wwol isn't built to
face the internet directly, and hardening it for that isn't worth the effort
for a project this small.

## 1. Prepare the PC you want to wake

For every PC:

1. **BIOS/UEFI:** enable Wake-on-LAN. The setting may be called "Wake on LAN",
   "Power On By PCI-E", or "Resume by LAN". If there is an "ErP Ready" or
   "Deep Sleep" option, disable it — it cuts power to the network card.
2. **Use wired Ethernet.** Wake-on-LAN over Wi-Fi almost never works. The cable
   can go to your router, or straight into the Pi (see
   [Pi cabled straight to the PC](#pi-cabled-straight-to-the-pc)).
3. **For the online/offline indicator (optional):** the PC needs a fixed IP.
   On your home network, set a DHCP reservation in your router; for a cable
   straight into the Pi, see the section linked above.

Then follow the steps for the PC's operating system.

### Windows

1. **Network adapter:** Device Manager → Network adapters → your Ethernet
   adapter → Properties:
   - **Power Management:** tick "Allow this device to wake the computer" and
     "Only allow a magic packet to wake the computer".
   - **Advanced:** set "Wake on Magic Packet" to **Enabled** (and "Shutdown
     Wake-On-Lan" if it is listed).
2. **Turn off Fast Startup:** Control Panel → Power Options → Choose what the
   power buttons do → Change settings that are currently unavailable → untick
   "Turn on fast startup".
3. **Find the MAC address:** run `ipconfig /all` and copy the "Physical
   Address" of the Ethernet adapter, e.g. `AA-BB-CC-DD-EE-FF`.
4. **Let Windows answer ping** (only needed for the online/offline indicator).
   In an administrator PowerShell:
     ```powershell
     Get-NetFirewallRule -DisplayName "*Echo Request*ICMPv4-In*" | Enable-NetFirewallRule
     ```
     This enables every matching "Echo Request (ICMPv4-In)" rule, including
     the Public-network one. To limit it, enable only the Private-profile rule
     in "Windows Defender Firewall with Advanced Security" → Inbound Rules
     instead. On non-English Windows the rule names are translated, so the
     command may match nothing — enable the rule by hand there.

### Ubuntu

1. **Find the Ethernet port's name and MAC address:**
   ```sh
   ip link
   ```
   The wired port is usually called `enp…` or `eno…` (e.g. `enp5s0`); its MAC
   is the value after `link/ether`. Use that port name wherever `enp5s0`
   appears below.
2. **Check the card supports Wake-on-LAN:**
   ```sh
   sudo apt install -y ethtool
   sudo ethtool enp5s0 | grep -i wake
   ```
   `Supports Wake-on:` must include `g` (magic packet).
3. **Turn Wake-on-LAN on permanently.** If the cable goes straight into the
   Pi, skip this — the Ubuntu step in
   [Pi cabled straight to the PC](#pi-cabled-straight-to-the-pc) does it.
   - **Ubuntu Desktop (NetworkManager):** find the connection that uses the
     port, then turn Wake-on-LAN on for it:
     ```sh
     nmcli -f NAME,DEVICE connection show
     sudo nmcli connection modify "Wired connection 1" 802-3-ethernet.wake-on-lan magic
     sudo nmcli connection up "Wired connection 1"
     ```
     Replace `Wired connection 1` with the name shown next to your port.
   - **Ubuntu Server (netplan):** in the file under `/etc/netplan/` that
     configures the port, add `wakeonlan: true` under it, then run
     `sudo netplan apply`:
     ```yaml
     network:
       version: 2
       ethernets:
         enp5s0:
           dhcp4: true
           wakeonlan: true
     ```
4. **Check it survives a reboot:** reboot, then run
   `sudo ethtool enp5s0 | grep Wake-on`. It should say `Wake-on: g`.
5. **Ping:** nothing to do. Ubuntu's firewall (`ufw`) allows ping by default,
   even when it is turned on.

Shut the PC down normally (`sudo poweroff`) before testing a wake. If it won't
wake from off, try waking it from suspend (`systemctl suspend`) first: if that
works, the BIOS is cutting power to the network card when the PC is off.

## 2. Set up the Pi

### Raspberry Pi Zero with DietPi

1. Download the DietPi image for **Raspberry Pi 1 / Zero (ARMv6)** from
   <https://dietpi.com> and flash it to the SD card with Raspberry Pi Imager
   ("Use custom") or balenaEtcher.
2. *(Optional, before first boot)* Open `dietpi.txt` on the SD card's boot
   partition to make sure Ethernet is used and, if you like, set a static IP.
   Check the comments in the file for the current option names; at the time of
   writing they are:
   ```ini
   AUTO_SETUP_NET_ETHERNET_ENABLED=1
   AUTO_SETUP_NET_WIFI_ENABLED=0
   AUTO_SETUP_NET_USESTATIC=1
   AUTO_SETUP_NET_STATIC_IP=192.168.1.20
   AUTO_SETUP_NET_STATIC_MASK=255.255.255.0
   AUTO_SETUP_NET_STATIC_GATEWAY=192.168.1.1
   AUTO_SETUP_NET_STATIC_DNS=192.168.1.1
   ```
   Skip the static-IP lines if you'd rather reserve the Pi's IP in your router.
3. Plug the USB-Ethernet adapter into the micro-USB port marked **USB** (not
   **PWR IN**) using an OTG adapter, connect the network cable, then power on.
   The first boot takes several minutes while DietPi updates itself.
4. Find the Pi's IP in your router, then SSH in: `ssh root@<pi-ip>` (default
   password `dietpi`). Finish DietPi's first-run setup and change the passwords
   when asked.
5. Check the adapter is up:
   ```sh
   ip -4 addr show eth0
   ```
   You should see an `inet` line. If `eth0` doesn't exist, run `ip link` to see
   the adapter's name (some appear as `enx…`), and use `dietpi-config` →
   Network Options: Adapters to enable Ethernet.
6. Install the packages wwol needs:
   ```sh
   apt update
   apt install -y python3 iputils-ping git
   ```

On DietPi you are logged in as `root`, so leave `sudo` off the commands in the
rest of this guide.

### Raspberry Pi 3B with Raspberry Pi OS Lite

1. Flash **Raspberry Pi OS Lite** with Raspberry Pi Imager. In Imager's
   settings, set a hostname and user and enable SSH.
2. Connect the Pi's Ethernet to your router (recommended), boot, and SSH in.
   If instead the Pi's Ethernet goes straight to the PC and the Pi uses Wi-Fi,
   also follow [Pi cabled straight to the PC](#pi-cabled-straight-to-the-pc).
3. Install the packages (usually already present):
   ```sh
   sudo apt update
   sudo apt install -y python3 iputils-ping git
   ```
4. Reserve the Pi's IP in your router so the web address doesn't change.

## 3. Install wwol

Get the code onto the Pi, either with git:

```sh
git clone <your-repo-url> wwol
cd wwol
```

or by copying it from your PC (run this on the PC):

```powershell
# DietPi (logs in as root)
scp -r C:\GitProjects\wwol root@<pi-ip>:/root/wwol
# Raspberry Pi OS (root login is disabled; use your user)
scp -r C:\GitProjects\wwol <user>@<pi-ip>:~/wwol
```

Don't put the code directly in `/opt/wwol` — that's where the installer
copies it to, and it will refuse to run from there.

Then, in the `wwol` directory on the Pi:

```sh
sudo sh install.sh
```

The installer:
- checks that `python3` (3.7+) and `ping` are installed
- creates a `wwol` system user
- copies the app to `/opt/wwol`
- creates `/opt/wwol/config.json` from the example (an existing config is never overwritten)
- installs and starts the `wwol` systemd service, which starts on boot

## 4. Configure your PCs

1. Find the broadcast address of the network your PC's Ethernet port is on.
   On the Pi, list its addresses:
   ```sh
   ip -4 addr
   ```
   Find the adapter on the same network as the PC (`eth0` for a wired Pi,
   `wlan0` for Wi-Fi). In `inet 192.168.1.20/24 brd 192.168.1.255`, the
   broadcast address is the value after `brd`: `192.168.1.255`.

   If the PC's Ethernet cable goes straight into the Pi rather than to your
   router, this won't work — see
   [Pi cabled straight to the PC](#pi-cabled-straight-to-the-pc) instead.
2. Edit the config:
   ```sh
   sudo nano /opt/wwol/config.json
   ```
   ```json
   {
     "host": "0.0.0.0",
     "port": 8080,
     "broadcast": "192.168.1.255",
     "devices": [
       { "name": "Gaming PC", "mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.1.50" },
       { "name": "Media PC", "mac": "11-22-33-44-55-66" }
     ]
   }
   ```

   | Field | Required | Default | Meaning |
   |---|---|---|---|
   | `host` | no | `0.0.0.0` | Network interface the web page listens on (`0.0.0.0` = all) |
   | `port` | no | `8080` | Web page port |
   | `broadcast` | yes | — | Broadcast address used for all PCs |
   | `devices[].name` | yes | — | Name shown on the page |
   | `devices[].mac` | yes | — | PC's MAC address; `AA:BB:…`, `AA-BB-…` and `AABB…` all work |
   | `devices[].ip` | no | — | PC's IP, used for the online/offline indicator |
   | `devices[].broadcast` | no | top-level `broadcast` | Override for a PC on another subnet |
   | `devices[].wol_port` | no | `9` | UDP port for the magic packet (some PCs use `7`) |
   | `devices[].interface` | no | — | Pi's Ethernet port the PC is cabled straight into, e.g. `eth0`; enables the standby/nolink status (see [Pi cabled straight to the PC](#pi-cabled-straight-to-the-pc)) |

3. Restart and check it started:
   ```sh
   sudo systemctl restart wwol
   systemctl status wwol
   ```

### Pi cabled straight to the PC

Use this when the Pi's Ethernet port is plugged directly into the PC, with no
router or switch in between, and the Pi reaches your network over Wi-Fi.

The magic packet has to go down that cable, but nothing on the cable hands out
IP addresses. So give the cable its own tiny network: the Pi is `10.0.0.1`,
the PC is `10.0.0.2`, and the broadcast address is `10.0.0.255`. (If your home
network already uses `10.0.0.x`, pick another range such as `192.168.50.x`
and adjust every address below.)

**1. Give the Pi's Ethernet port a fixed address.** Turn the PC on first so
the cable has a link. Then follow the steps for your Pi:

- **Raspberry Pi OS Bookworm or newer** (`systemctl is-active NetworkManager`
  prints `active`):
  ```sh
  sudo nmcli connection add type ethernet ifname eth0 con-name wwol-direct \
      ipv4.method manual ipv4.addresses 10.0.0.1/24 ipv4.never-default yes \
      ipv6.method disabled connection.autoconnect-priority 10
  sudo nmcli connection up wwol-direct
  ```
  `ipv4.never-default yes` keeps the Pi's internet traffic on Wi-Fi. Run
  `nmcli connection show` to check `wwol-direct` is active on `eth0`.

- **Older Raspberry Pi OS (Bullseye)**, which uses dhcpcd: add these lines to
  the end of `/etc/dhcpcd.conf` (`sudo nano /etc/dhcpcd.conf`), then run
  `sudo systemctl restart dhcpcd`:
  ```
  interface eth0
  static ip_address=10.0.0.1/24
  ```
  There is deliberately no `static routers=` line, so the Pi's internet
  traffic stays on Wi-Fi.

- **DietPi:** in `/etc/network/interfaces` (`nano /etc/network/interfaces`),
  replace the `eth0` section with the lines below and leave the `wlan0`
  section alone. Then run `ifdown eth0; ifup eth0`, or reboot.
  ```
  auto eth0
  iface eth0 inet static
      address 10.0.0.1
      netmask 255.255.255.0
  ```
  Don't add a `gateway` line, or the Pi's internet traffic will go down the
  cable instead of over Wi-Fi. Changing network settings in `dietpi-config`
  later may rewrite this file, so check it afterwards.

Check it worked:
```sh
ip -4 addr show eth0
```
You should see `inet 10.0.0.1/24 brd 10.0.0.255`.

**2. Set up the PC's Ethernet port.** The PC gets the fixed address `10.0.0.2`
with no gateway, so it keeps using its usual connection (e.g. Wi-Fi) for the
internet.

- **Windows** (optional — only needed for the online/offline indicator;
  waking works without it): open Settings → Network & internet → Ethernet →
  IP assignment → Edit → Manual, turn IPv4 on, and set IP address `10.0.0.2`
  and subnet mask `255.255.255.0` (or prefix length `24`). Leave gateway and
  DNS empty.

  Windows will call this link an "Unidentified network" and treat it as
  Public, so the ping rule from the [Windows](#windows) steps must be enabled
  for the Public profile. The one-liner there does that.

- **Ubuntu Desktop (NetworkManager):** this also turns Wake-on-LAN on. Replace
  `enp5s0` with your port's name (see the [Ubuntu](#ubuntu) steps):
  ```sh
  sudo nmcli connection add type ethernet ifname enp5s0 con-name wwol-direct \
      ipv4.method manual ipv4.addresses 10.0.0.2/24 ipv4.never-default yes \
      ipv6.method disabled 802-3-ethernet.wake-on-lan magic \
      connection.autoconnect-priority 10
  sudo nmcli connection up wwol-direct
  ```
  If you got the port name wrong, fix it with
  `sudo nmcli connection modify wwol-direct connection.interface-name <port>`
  and run the `up` command again. Check with `ip -4 addr show enp5s0`: you
  should see `inet 10.0.0.2/24`.

- **Ubuntu Server (netplan):** create `/etc/netplan/60-wwol.yaml`, then run
  `sudo chmod 600 /etc/netplan/60-wwol.yaml` and `sudo netplan apply`:
  ```yaml
  network:
    version: 2
    ethernets:
      enp5s0:
        dhcp4: false
        addresses: [10.0.0.2/24]
        wakeonlan: true
  ```

On Ubuntu, reboot and check `sudo ethtool enp5s0 | grep Wake-on` says
`Wake-on: g`.

**3. Point wwol at the cable's network.** In `/opt/wwol/config.json`:
```json
{
  "host": "0.0.0.0",
  "port": 8080,
  "broadcast": "10.0.0.255",
  "devices": [
    { "name": "Work PC", "mac": "28:D0:43:D7:F0:25", "ip": "10.0.0.2",
      "interface": "eth0" }
  ]
}
```
Use your PC's own MAC. Leave out `"ip"` if you skipped step 2. If you also have
PCs plugged into your router, keep your home network's broadcast address at
the top level and give only this PC `"broadcast": "10.0.0.255"`.

`"interface"` is the Pi's Ethernet port the cable is plugged into (`eth0`, or
the `enx…` name of a USB adapter — see `ip link`). With it set, wwol also
watches the cable itself, so when the PC is off the page can tell **standby**
(network card powered and listening, ready to wake) from **nolink** (no power
to the card, so a wake won't work). The page shows the port under the PC's
name. Without `"ip"`, the PC can't be shown as online: a running PC also shows
standby. The installer never changes an existing config, so add `"interface"`
by hand after updating.

**More than one PC cabled to the Pi:** each PC needs its own Pi port (e.g. a
USB-Ethernet adapter as a second port) and its own tiny network, such as
`10.0.1.x` on the second cable. Repeat steps 1 and 2 for that port and PC, and
give the PC its own `"broadcast"` (e.g. `"10.0.1.255"`) and `"interface"`.

Restart with `sudo systemctl restart wwol`. The page is still at
`http://<Pi's Wi-Fi IP>:8080` (run `hostname -I` on the Pi to see it).

**4. Check the link stays up while the PC is off.** Shut the PC down and wait
for the page to refresh:

- **standby** means the PC's network card is still powered and listening, so
  waking will work.
- **nolink** means the card is losing power when the PC is off: recheck the
  BIOS Wake-on-LAN and "ErP" settings, and the Windows or Ubuntu steps, in
  section 1. Also check `"interface"` names the right port.

If you didn't set `"interface"`, check from the Pi instead:
```sh
ip link show eth0
```
`LOWER_UP` in the output means the card is listening; `NO-CARRIER` means it
has lost power.

## 5. Use it

Open `http://<pi-ip>:8080` on your phone or PC.

| Status | Meaning |
|---|---|
| green **online** | the PC answers ping |
| red **offline** | no answer to ping |
| yellow **waking** | magic packet sent; waiting up to 2 minutes for the PC to come online |
| outlined **unknown** | no `ip` set in the config, so status can't be checked |
| teal **standby** | only with `interface` set: no answer to ping, but the cable has a link, so the PC's network card is powered and ready to wake |
| grey outlined **nolink** | only with `interface` set: no answer to ping and no link on the cable, so a wake won't work |

With `interface` set, standby and nolink replace offline and unknown.

The page refreshes every 10 seconds.

## Managing wwol

| Task | Command |
|---|---|
| Status | `systemctl status wwol` |
| Live logs | `journalctl -u wwol -f` |
| Restart after editing config | `sudo systemctl restart wwol` |
| Update | `cd wwol && git pull && sudo sh install.sh` |

Uninstall:
```sh
sudo systemctl disable --now wwol
sudo rm /etc/systemd/system/wwol.service
sudo systemctl daemon-reload
sudo rm -rf /opt/wwol
sudo userdel wwol
```

## Troubleshooting

**The PC doesn't wake up**
- Check the logs show `Sent magic packet to …`: `journalctl -u wwol -n 20`.
- Double-check the MAC address and the `broadcast` address.
- The PC must be on wired Ethernet. On Windows, Fast Startup must be off; on
  Ubuntu, `sudo ethtool <port> | grep Wake-on` must say `Wake-on: g`.
- If the PC is cabled straight into the Pi, the page must show **standby**
  while the PC is off (or, without `"interface"` set, `ip link show eth0` on
  the Pi must show `LOWER_UP`).
- Try waking it from sleep first. If that works but waking from shut down
  doesn't, look for "ErP" / "Deep Sleep" in the BIOS and disable it.
- Some PCs listen on port 7: set `"wol_port": 7` on that device.

**Status is always offline**
- Check the `ip` in the config is the PC's current IP.
- From the Pi, run `ping -c 1 <pc-ip>`. If that fails too, on Windows allow
  ping in the firewall (see the [Windows](#windows) steps); on Ubuntu, check
  for custom `ufw` rules that block ping (`sudo ufw status verbose`).
- A PC cabled straight to the Pi shows offline rather than standby or nolink:
  its entry in `/opt/wwol/config.json` has no `"interface"`, or the new code
  isn't installed. Re-run `sudo sh install.sh`, add `"interface"`, and restart.

**Status is always unknown**
- That device has no `ip` in the config.

**The page won't load**
- `systemctl status wwol` — is it running?
- `journalctl -u wwol -n 50` — look for `Config error: …`, which names the
  field that's wrong, or `Cannot listen on …` if another program uses the port.

**Pi Zero: the USB-Ethernet adapter isn't detected**
- Make sure it's in the **USB** port, not **PWR IN**, and that the OTG adapter
  is a data adapter.
- `dmesg | tail -n 30` shows driver messages right after plugging it in.
- `lsusb` should list the adapter (install it with `apt install -y usbutils`
  if the command is missing).

## Development

```sh
python -m unittest discover -s tests -v   # run the tests
cp config.example.json config.json        # local config (git-ignored)
python -m wwol.server                     # http://127.0.0.1:8080
```

On Windows the status shows offline because Windows `ping` uses different
flags, and devices with `interface` show nolink because there is no `/sys`;
the rest works.
